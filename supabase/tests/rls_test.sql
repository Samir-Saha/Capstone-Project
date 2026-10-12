-- RLS tests. Run after the shim and the core migration on a scratch database.
-- Any failed expectation raises and stops the script (psql -v ON_ERROR_STOP=1).

grant usage on schema public to anon, authenticated, service_role;
grant select, insert, update, delete on all tables in schema public to authenticated, service_role;
grant select on all tables in schema public to anon;

-- Two users, Alice and Bob
insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-00000000000a', 'alice@example.edu'),
  ('00000000-0000-0000-0000-00000000000b', 'bob@example.edu');

do $$ begin
  assert (select count(*) from profiles) = 2, 'signup trigger should create profiles';
end $$;

-- Backend (service role) seeds data for Alice
set role service_role;
insert into courses (id, owner_id, name) values ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-00000000000a', 'Calc 2');
insert into topics (id, course_id, owner_id, name) values
  ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-00000000000a', 'Integration by parts');
insert into questions (id, course_id, topic_id, owner_id, kind, difficulty, statement, verification_status, prompt_version) values
  ('30000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-00000000000a', 'symbolic', 2, 'Integrate x cos x', 'verified', 'q-1'),
  ('30000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-00000000000a', 'numeric', 2, 'Rejected one', 'pending', 'q-1');
update questions set verification_status = 'rejected' where id = '30000000-0000-0000-0000-000000000002';
insert into question_keys (question_id, answer, explanation) values ('30000000-0000-0000-0000-000000000001', 'x*sin(x) + cos(x)', 'parts');
insert into coding_problems (id, slug, title, pattern, difficulty, statement, signature, verification_status) values
  ('40000000-0000-0000-0000-000000000001', 'p1', 'P1', 'graphs', 'easy', 's', 'def solve()', 'verified');
insert into coding_test_cases (problem_id, ordinal, args, expected, hidden) values ('40000000-0000-0000-0000-000000000001', 1, '[1]', '2', true);
insert into xp_events (owner_id, reason, amount, source_type, source_id) values
  ('00000000-0000-0000-0000-00000000000a', 'exam_correct', 10, 'exam_attempt', '50000000-0000-0000-0000-000000000001');
reset role;

-- A final verification status can't change
do $$ begin
  begin
    update questions set verification_status = 'verified' where id = '30000000-0000-0000-0000-000000000002';
    raise exception 'TEST FAILED: rejected question was re-verified';
  exception when raise_exception then
    if sqlerrm like 'TEST FAILED%' then raise; end if;
  end;
end $$;

-- Duplicate XP for the same event is refused
do $$ begin
  begin
    insert into xp_events (owner_id, reason, amount, source_type, source_id) values
      ('00000000-0000-0000-0000-00000000000a', 'exam_correct', 10, 'exam_attempt', '50000000-0000-0000-0000-000000000001');
    raise exception 'TEST FAILED: duplicate XP accepted';
  exception when unique_violation then null;
  end;
end $$;

-- ---------------------------------------------------------------- as Alice
set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000a', false);

do $$ begin
  assert (select count(*) from courses) = 1, 'alice sees her course';
  assert (select count(*) from questions) = 1, 'alice sees only her published question';
  assert (select count(*) from question_keys) = 0, 'answer keys are invisible to clients';
  assert (select count(*) from coding_test_cases) = 0, 'hidden tests are invisible to clients';
  assert (select count(*) from coding_problems) = 1, 'verified problems are visible';
  assert (select xp from player_summary where owner_id = auth.uid()) = 10, 'summary view reads own xp';
end $$;

-- Alice can't award herself XP or forge an attempt
do $$ begin
  begin
    insert into xp_events (owner_id, reason, amount, source_type, source_id) values
      ('00000000-0000-0000-0000-00000000000a', 'cheat', 1000, 'x', gen_random_uuid());
    raise exception 'TEST FAILED: client inserted XP';
  exception when insufficient_privilege then null;
  end;
end $$;

-- Alice can create a course for herself but not for Bob
insert into courses (name) values ('Kinematics');
do $$ begin
  begin
    insert into courses (owner_id, name) values ('00000000-0000-0000-0000-00000000000b', 'Planted');
    raise exception 'TEST FAILED: course created for another user';
  exception when insufficient_privilege then null;
  end;
end $$;

-- ---------------------------------------------------------------- as Bob
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-00000000000b', false);

do $$ begin
  assert (select count(*) from courses) = 0, 'bob cannot see alice''s courses';
  assert (select count(*) from questions) = 0, 'bob cannot see alice''s questions';
  assert (select count(*) from xp_events) = 0, 'bob cannot see alice''s xp';
  assert (select count(*) from profiles) = 1, 'bob sees only his own profile';
end $$;

update courses set name = 'hijacked' where id = '10000000-0000-0000-0000-000000000001';
reset role;
do $$ begin
  assert (select name from courses where id = '10000000-0000-0000-0000-000000000001') = 'Calc 2', 'bob could not rename alice''s course';
end $$;

-- ---------------------------------------------------------------- anonymous
set role anon;
select set_config('request.jwt.claim.sub', '', false);
do $$ begin
  assert (select count(*) from courses) = 0, 'anon sees nothing';
  assert (select count(*) from coding_problems) = 0, 'anon sees no problems';
end $$;
reset role;

select 'ALL RLS TESTS PASSED' as result;
