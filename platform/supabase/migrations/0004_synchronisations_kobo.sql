-- AGST Platform -- Tracabilite des synchronisations KoboToolbox
-- Complement a 0001 (table `synchronisations` liee a `projets`, pas
-- encore utilisee en pratique par le code) et 0002/0003 (jobs/fichiers
-- par client_id direct) : cette table trace chaque tentative de
-- synchronisation Kobo par client_id + identifiant de projet Kobo
-- (uid cote Kobo, pas un uuid Supabase), coherente avec le modele
-- deja en place pour jobs/fichiers plutot que le modele organisation
-- de 0001 (pas encore utilise par aucune route reelle a ce jour).

create table if not exists synchronisations_kobo (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references auth.users(id) on delete cascade,
    kobo_project_uid text not null,       -- identifiant Kobo (asset uid), pas un uuid Supabase
    job_id text,                          -- reference libre vers jobs.job_id si issu d'un job explicite
    demarree_le timestamptz not null default now(),
    terminee_le timestamptz,
    statut text not null default 'en_cours' check (statut in ('en_cours', 'succes', 'echec')),
    n_soumissions_recuperees integer,
    n_soumissions_nouvelles integer,
    n_soumissions_modifiees integer,
    n_soumissions_inchangees integer,
    erreur text                           -- message tronque, jamais le token
);

alter table synchronisations_kobo enable row level security;

create policy synchronisations_kobo_isolation on synchronisations_kobo for all
    using (client_id = auth.uid())
    with check (client_id = auth.uid());

create index if not exists idx_sync_kobo_client on synchronisations_kobo(client_id);
create index if not exists idx_sync_kobo_projet on synchronisations_kobo(kobo_project_uid);
