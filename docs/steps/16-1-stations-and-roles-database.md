# Step 16, phase R-2: police stations and the seven role names (database)

> **Written before the plain case design (2026-11-10).** Where this note says repository, clone, branch or commit, read *case*: see [../case-management/13-plain-case-design.md](../case-management/13-plain-case-design.md).

Design: [docs/case-management/12-roles-and-stations.md](../case-management/12-roles-and-stations.md). Built 2026-11-10.

1. **What this phase does.** It gives the database the *places* (police stations) and the *names* (seven roles) the new design needs. It
   does not yet limit who sees what by station: that is phase R-3. Nothing a user can do changed.
2. **Police stations.** New table `police_stations` (code, name, district, status). Stations are never deleted; one that no longer
   works is marked inactive. Every organisation got a default station, **HQ**.
3. **Which station a user may see.** New table `user_stations`. A Super Admin needs no row (sees every station). Everybody else got a
   row for HQ, so what they see is unchanged. A row is ended (revoked), never deleted.
4. **The officer list.** New table `officer_registry` (officer ID, name, rank, station, highest role) and `users.officer_id`. In phase
   R-4 an account can be made only for an officer in this list. Accounts made before now have no officer yet.
5. **Every case has a station.** New column `case_families.station_id`; all existing cases (all 6 in the development database)
   were put in HQ. New cases take the station given in the request (`station_id`, optional) or the default station. It is set once and
   can't change (the database refuses).
6. **The seven roles.** `super_admin`, `administrator`, `supervisor`, `investigator`, `sub_investigator`, `analyst`, `viewer`. The old
   `platform_admin` is now `super_admin` (same powers: the whole organisation). `administrator` and `sub_investigator` exist but have
   no special rules yet (R-3). Inside a case the stored roles are unchanged; screens call `contributor` "Sub Investigator" and `lead`
   "Investigator (case lead)".
7. **History is untouched.** Old audit events still say `platform_admin`; no commit, membership or evidence record was changed.
8. **Protection.** The three new tables follow the same rule as the other case tables: the application's database login can read,
   add and update the allowed columns, but never delete (migration 0016 refreshes its rights).
9. **How it was checked.** The migration was applied, rolled back and applied again on the test database; all 525 backend tests and
   the 50 frontend tests pass; the models and the migration agree (automatic check). Before changing the real development database a
   backup was made: `backups/<date>-before-0016/casesdb.dump`. After the Docker rebuild: version 0016, 6 of 6 cases in HQ, 7 of 7
   accounts kept their access.
10. **What comes next.** R-3: station scope in the access rules (who sees what), who may create whom, the officer-ID check, and the
    promotion rule. To go back: `alembic downgrade 0015` (development only: station links are lost).
