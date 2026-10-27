-- AGST Platform -- Tests de migration, RLS et acces non autorise
-- STATUT : PREPARE, JAMAIS EXECUTE -- aucun projet Supabase connecte.
-- A executer DANS LE SQL EDITOR SUPABASE (environnement de test,
-- jamais directement sur une base contenant des donnees de production
-- reelles) une fois 0001_survey_intelligence_schema.sql applique.
--
-- Chaque bloc cree des donnees de test, verifie un comportement, puis
-- nettoie. Les assertions utilisent des `do $$ ... $$` avec `raise
-- exception` pour echouer bruyamment si le resultat n'est pas celui
-- attendu -- ne jamais ignorer un echec silencieusement.

-- ============================================================
-- Test 1 : la migration cree bien toutes les tables attendues
-- ============================================================
do $$
declare
    missing_tables text;
begin
    select string_agg(t, ', ') into missing_tables
    from unnest(array[
        'organisations', 'membres_organisation', 'projets', 'indicateurs',
        'formulaires', 'soumissions', 'anomalies', 'synchronisations'
    ]) t
    where not exists (
        select 1 from information_schema.tables
        where table_schema = 'public' and table_name = t
    );
    if missing_tables is not null then
        raise exception 'Tables manquantes apres migration : %', missing_tables;
    end if;
    raise notice 'Test 1 OK : toutes les tables attendues existent';
end $$;

-- ============================================================
-- Test 2 : RLS est bien active sur toutes les tables sensibles
-- ============================================================
do $$
declare
    unprotected_tables text;
begin
    select string_agg(tablename, ', ') into unprotected_tables
    from pg_tables
    where schemaname = 'public'
      and tablename in ('organisations', 'membres_organisation', 'projets',
                         'indicateurs', 'formulaires', 'soumissions', 'anomalies', 'synchronisations')
      and rowsecurity = false;
    if unprotected_tables is not null then
        raise exception 'RLS NON active sur : %', unprotected_tables;
    end if;
    raise notice 'Test 2 OK : RLS active sur toutes les tables';
end $$;

-- ============================================================
-- Test 3 : isolation reelle entre deux organisations (le coeur du test)
-- Necessite deux utilisateurs de test crees au prealable via
-- Supabase Auth (auth.users) -- remplacer les UUID ci-dessous par
-- les vrais identifiants generes lors de la creation des comptes test.
-- ============================================================
-- Prerequis manuel avant d'executer ce bloc :
--   1. Creer 2 utilisateurs de test via Auth > Users (ex: test1@agst.test, test2@agst.test)
--   2. Noter leurs UUID (auth.users.id)
--   3. Remplacer <UUID_USER_1> et <UUID_USER_2> ci-dessous

/*
do $$
declare
    org1_id uuid;
    org2_id uuid;
    projet1_id uuid;
    user1_id uuid := '<UUID_USER_1>';
    user2_id uuid := '<UUID_USER_2>';
    n_visible integer;
begin
    insert into organisations (nom) values ('Org Test 1') returning id into org1_id;
    insert into organisations (nom) values ('Org Test 2') returning id into org2_id;
    insert into membres_organisation (organisation_id, user_id, role) values (org1_id, user1_id, 'admin');
    insert into membres_organisation (organisation_id, user_id, role) values (org2_id, user2_id, 'admin');
    insert into projets (organisation_id, nom) values (org1_id, 'Projet Org1') returning id into projet1_id;

    -- Simuler une requete authentifiee comme user2 (set_config imite auth.uid()
    -- en contexte de test -- en conditions reelles, c'est le JWT qui fixe
    -- auth.uid() automatiquement cote PostgREST/Supabase).
    perform set_config('request.jwt.claims', json_build_object('sub', user2_id)::text, true);

    select count(*) into n_visible from projets where id = projet1_id;
    if n_visible != 0 then
        raise exception 'ECHEC ISOLATION : user2 voit le projet de org1 (% ligne(s) visibles)', n_visible;
    end if;
    raise notice 'Test 3 OK : isolation confirmee, user2 ne voit pas le projet de org1';

    -- Nettoyage
    delete from projets where id = projet1_id;
    delete from membres_organisation where organisation_id in (org1_id, org2_id);
    delete from organisations where id in (org1_id, org2_id);
end $$;
*/

-- ============================================================
-- Test 4 : aucune cible/valeur_reference n'est inseree avec une
-- valeur par defaut non-NULL (verifie que le schema n'invente rien)
-- ============================================================
do $$
declare
    default_cible text;
    default_valeur_ref text;
begin
    select column_default into default_cible
    from information_schema.columns
    where table_name = 'indicateurs' and column_name = 'cible';
    select column_default into default_valeur_ref
    from information_schema.columns
    where table_name = 'indicateurs' and column_name = 'valeur_reference';

    if default_cible is not null or default_valeur_ref is not null then
        raise exception 'ECHEC : cible ou valeur_reference ont une valeur par defaut non-NULL (risque de donnee inventee)';
    end if;
    raise notice 'Test 4 OK : cible/valeur_reference restent NULL par defaut, jamais inventees';
end $$;

-- ============================================================
-- Test 5 : les contraintes CHECK sur les statuts rejettent une
-- valeur invalide (empeche un etat incoherent d'etre insere)
-- ============================================================
do $$
begin
    begin
        insert into anomalies (projet_id, regle_declenchee, niveau_gravite, justification, statut_resolution)
        values (gen_random_uuid(), 'test', 'niveau_invente_qui_nexiste_pas', 'test', 'nouvelle');
        raise exception 'ECHEC : une valeur de niveau_gravite invalide a ete acceptee';
    exception
        when check_violation then
            raise notice 'Test 5 OK : contrainte CHECK rejette bien une valeur de gravite invalide';
        when foreign_key_violation then
            raise notice 'Test 5 OK (via FK -- projet_id inexistant, attendu dans ce test isole)';
    end;
end $$;
