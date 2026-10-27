-- AGST Platform -- Table generique de suivi des jobs (orchestrateur)
-- Complement a 0001 (specifique Survey Intelligence) : cette table
-- trace l'execution de TOUS les agents (pas seulement survey_intelligence),
-- pour repondre au risque identifie a l'audit preproduction : le
-- stockage de metadata de job est actuellement UNIQUEMENT fichier
-- local (job_meta.json), sans aucune vue consolidee/interrogeable,
-- et perdu si le disque est perdu.
--
-- Choix de conception : client_id = auth.uid() directement (pas de
-- notion d'organisation ici, contrairement a 0001) car job_runner.py
-- est utilise par les 8 agents generiques, dont la plupart n'ont pas
-- encore de notion d'organisation/equipe -- a faire evoluer plus tard
-- si un agent necessite un partage d'equipe.

create table if not exists jobs (
    id uuid primary key default gen_random_uuid(),
    job_id text not null unique,        -- identifiant court genere par storage.py (new_job_dir)
    client_id uuid not null references auth.users(id) on delete cascade,
    agent text not null,
    statut text not null default 'en_cours' check (
        statut in ('en_cours', 'termine', 'erreur', 'timeout')
    ),
    cli_args jsonb,
    code_retour integer,
    duree_secondes numeric,
    erreur text,
    demarre_le timestamptz not null default now(),
    termine_le timestamptz
);

alter table jobs enable row level security;

create policy jobs_isolation on jobs for all
    using (client_id = auth.uid())
    with check (client_id = auth.uid());

create index if not exists idx_jobs_client on jobs(client_id);
create index if not exists idx_jobs_agent on jobs(agent);
create index if not exists idx_jobs_statut on jobs(statut);
