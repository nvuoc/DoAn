"""Disposable in-memory SQL checks. Never migrate an existing database."""
import argparse, json, sqlite3
from pathlib import Path
root = Path(__file__).resolve().parents[1]
c = sqlite3.connect(':memory:')
c.executescript((root/'examples/storage-target.sql').read_text(encoding='utf-8-sig'))
checks=[]
def ok(name, condition):
    if not condition: raise AssertionError(name)
    checks.append(name)
def rejected(name, sql, values=()):
    try:
        with c:
            c.execute(sql,values)
    except sqlite3.IntegrityError:
        checks.append(name)
    else:
        raise AssertionError(name+' was accepted')
now=1792368000.0
for n in (1,2):
    c.execute('INSERT INTO core_sessions VALUES (?,?,?,?,?,?)',(f's{n}','voice','synthetic-scope','active',now,None))
    c.execute('INSERT INTO core_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'r{n}','core-next','design-only',1,'{}','ai',f's{n}',1,0,'collecting','{}',now,now,now+900))
    c.execute('INSERT INTO core_request_sessions VALUES (?,?,?,?,?)',(f'r{n}',f's{n}',1,'synthetic-scope',now))
    c.execute('INSERT INTO core_drafts VALUES (?,?,?,?,?,?,?)',(f'd{n}',f'r{n}',0,1,'{}','{}',now))
    c.execute('INSERT INTO core_inputs VALUES (?,?,?,?,?,?,?,?)',(f'r{n}',f'i{n}','user_turn','a'*64,f's{n}','{"raw_text":"synthetic"}','{}',now))
    c.execute('INSERT INTO core_turns(turn_id,request_id,input_id,session_id,expected_state_version,captured_owner_generation,phase,expires_at_utc,created_at_utc) VALUES (?,?,?,?,?,?,?,?,?)',(f't{n}',f'r{n}',f'i{n}',f's{n}',0,1,'preparing',now+8,now))
c.commit()
ok('DDL creates all tables; foreign_keys enabled',c.execute('PRAGMA foreign_keys').fetchone()[0]==1)
rejected('one active draft per request','INSERT INTO core_drafts VALUES (?,?,?,?,?,?,?)',('d3','r1',0,1,'{}','{}',now))
rejected('input identity unique','INSERT INTO core_inputs VALUES (?,?,?,?,?,?,?,?)',('r1','i1','user_turn','b'*64,'s1','{}','{}',now))
def writes(outbox_payload):
    result=c.execute("UPDATE core_requests SET state_version=1,booking_status='request_recorded' WHERE request_id='r1' AND state_version=0 AND owner_generation=1")
    assert result.rowcount==1
    c.execute('INSERT INTO core_operations(operation_id,request_id,draft_id,booking_revision,operation_kind,idempotency_key,payload_hash,protected_payload_json,phase,outcome_json,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',('o1','r1','d1',0,'local_intake','r1:d1:0:local_intake','a'*64,'{}','succeeded','{"kind":"request_recorded"}',now,now))
    c.execute('INSERT INTO sample_bookings VALUES (?,?,?,?,?,?,?,?,?,?)',('b1','r1','d1','o1','s1',0,'confirmed','not_integrated','{}',now))
    c.execute('INSERT INTO sample_operator_tasks VALUES (?,?,?,?,?,?,?,?,?)',('task1','b1','new_booking',None,'open',0,'{}',now,now))
    c.execute('INSERT INTO core_responses VALUES (?,?,?,?,?,?,?,?)',('resp1','t1','r1',1,0,'[]','{}',now))
    c.execute('INSERT INTO sample_dashboard_outbox(event_id,request_id,topic,payload_json,phase,created_at_utc) VALUES (?,?,?,?,?,?)',('e1','r1','booking.recorded',outbox_payload,'pending',now))
    c.execute("UPDATE core_turns SET phase='committed',committed_state_version=1,result_json=?,completed_at_utc=? WHERE turn_id='t1'",('{"status":"committed"}',now))
try:
    with c:
        writes('not-json')
except sqlite3.IntegrityError:
    pass
else:
    raise AssertionError('injected transaction failure did not fail')
tables=['core_operations','sample_bookings','sample_operator_tasks','core_responses','sample_dashboard_outbox']
ok('atomic rollback of domain booking task response outbox',all(c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]==0 for t in tables) and c.execute("SELECT state_version FROM core_requests WHERE request_id='r1'").fetchone()[0]==0)
with c:
    writes('{}')
ok('atomic retry succeeds after rollback',all(c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]==1 for t in tables))
rejected('durable operation tuple rejects new key retry','INSERT INTO core_operations(operation_id,request_id,draft_id,booking_revision,operation_kind,idempotency_key,payload_hash,protected_payload_json,phase,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?)',('o2','r1','d1',0,'local_intake','different-key','a'*64,'{}','prepared',now,now))
rejected('one new-booking task','INSERT INTO sample_operator_tasks VALUES (?,?,?,?,?,?,?,?,?)',('task2','b1','new_booking',None,'open',0,'{}',now,now))
with c:
    c.execute('INSERT INTO core_questions VALUES (?,?,?,?,?,?,?,?,?,?)',('q1','r1','confirm_trip','d1',0,None,'pending','{}',now+30,now))
rejected('one pending question','INSERT INTO core_questions VALUES (?,?,?,?,?,?,?,?,?,?)',('q2','r1','confirm_trip','d1',0,None,'pending','{}',now+30,now))
rejected('cross-request operation cannot reference another draft','INSERT INTO core_operations(operation_id,request_id,draft_id,booking_revision,operation_kind,idempotency_key,payload_hash,protected_payload_json,phase,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?)',('o3','r2','d1',1,'local_intake','foreign-key','a'*64,'{}','prepared',now,now))
ok('stale CAS affects zero rows',c.execute("UPDATE core_requests SET state_version=2 WHERE request_id='r1' AND state_version=0 AND owner_generation=1").rowcount==0)
with c:
    c.execute("UPDATE core_turns SET phase='cancelled' WHERE turn_id='t2'")
ok('cancelled turn cannot pass explicit durable guard',c.execute("UPDATE core_requests SET state_version=1 WHERE request_id='r2' AND state_version=0 AND owner_generation=1 AND EXISTS (SELECT 1 FROM core_turns t WHERE t.turn_id='t2' AND t.request_id=core_requests.request_id AND t.phase='preparing')").rowcount==0)
ok('owner generation stale guard affects zero rows',c.execute("UPDATE core_requests SET state_version=2 WHERE request_id='r1' AND state_version=1 AND owner_generation=0").rowcount==0)
with c:
    for index in (1, 2):
        c.execute('INSERT INTO core_operations(operation_id,request_id,draft_id,booking_revision,operation_kind,action_intent_id,idempotency_key,payload_hash,protected_payload_json,phase,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                  (f'h{index}','r2','d2',0,'handoff',f'intent{index}',f'handoff-key-{index}','a'*64,'{}','prepared',now,now))
ok('distinct handoff intents at one booking revision remain separate',c.execute("SELECT count(*) FROM core_operations WHERE request_id='r2' AND operation_kind='handoff'").fetchone()[0]==2)
rejected('handoff retry cannot change key to duplicate same intent','INSERT INTO core_operations(operation_id,request_id,draft_id,booking_revision,operation_kind,action_intent_id,idempotency_key,payload_hash,protected_payload_json,phase,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
         ('h3','r2','d2',0,'handoff','intent1','changed-handoff-key','a'*64,'{}','prepared',now,now))
with c:
    c.execute('INSERT INTO sample_support_requests VALUES (?,?,?,?,?,?,?,?)',('support1','r2','h1','open','unverified_pickup','{}',now,now))
ok('support before booking needs no fake booking record',c.execute("SELECT count(*) FROM sample_support_requests WHERE request_id='r2'").fetchone()[0]==1 and c.execute("SELECT count(*) FROM sample_bookings WHERE request_id='r2'").fetchone()[0]==0)
ok('SQLite integrity and foreign keys clean',c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and c.execute('PRAGMA foreign_key_check').fetchall()==[])
c.close()
result={'checks_passed':len(checks),'checks':checks,'database':':memory:','limitations':'SQL structure and explicit test queries only; no new runtime implemented'}
parser=argparse.ArgumentParser(description='Illustrative storage constraints, not core runtime tests')
parser.add_argument('--output',type=Path)
args=parser.parse_args()
if args.output:
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
