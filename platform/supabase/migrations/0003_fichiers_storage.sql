-- AGST Platform -- Metadonnees des fichiers Supabase Storage
-- Complement a 0001/0002 : trace chaque fichier importe/genere par
-- les agents, avec son emplacement reel dans Supabase Storage
-- (bucket prive "agst-files"), jamais le contenu binaire en base.
--
-- Isolation : client_id = auth.uid(), comme la table jobs (0002).
-- Projet/organisation optionnels (NULL si l'agent n'a pas encore de
-- notion de projet, ex: agents hors survey_intelligence).

create table if not exists fichiers (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references auth.users(id) on delete cascade,
    job_id text,                         -- reference libre vers jobs.job_id (pas de FK stricte : jobs peut etre nettoye independamment)
    projet_id uuid references projets(id) on delete set null,
    categorie text not null check (categorie in (
        'matrice_indicateurs', 'xlsform', 'soumissions_importees',
        'registre_alertes', 'rapport', 'fichier_source', 'autre'
    )),
    nom_original text not null,          -- nom fourni par l'utilisateur, jamais utilise comme cle de stockage
    cle_stockage text not null unique,   -- cle reelle dans le bucket, non previsible (uuid + extension)
    bucket text not null default 'agst-files',
    type_mime text,
    taille_octets bigint,
    checksum_sha256 text,
    cree_le timestamptz not null default now(),
    supprime_le timestamptz              -- suppression logique : jamais de DELETE physique immediat
);

alter table fichiers enable row level security;

create policy fichiers_isolation on fichiers for all
    using (client_id = auth.uid())
    with check (client_id = auth.uid());

create index if not exists idx_fichiers_client on fichiers(client_id);
create index if not exists idx_fichiers_job on fichiers(job_id);
create index if not exists idx_fichiers_projet on fichiers(projet_id);
create index if not exists idx_fichiers_categorie on fichiers(categorie);

-- ============================================================
-- Bucket Supabase Storage prive -- cree via l'API Storage
-- (POST /storage/v1/bucket), PAS via SQL, donc documente ici pour
-- reproductibilite mais a executer separement :
--   id=agst-files, public=false, file_size_limit=26214400 (25 Mo)
--   allowed_mime_types=[xlsx, csv, json, text/plain, pdf, docx]
-- ============================================================

-- Policies RLS sur storage.objects -- isolation par prefixe de
-- chemin : chaque objet doit etre stocke sous <client_id>/... et
-- auth.uid() doit correspondre exactement a ce premier segment.
-- C'est une DEFENSE SUPPLEMENTAIRE au niveau Storage, en plus du
-- controle d'autorisation applicatif fait par le backend (jamais
-- l'un sans l'autre).
drop policy if exists "fichiers_select_prefixe_client" on storage.objects;
create policy "fichiers_select_prefixe_client" on storage.objects
    for select using (
        bucket_id = 'agst-files'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

drop policy if exists "fichiers_insert_prefixe_client" on storage.objects;
create policy "fichiers_insert_prefixe_client" on storage.objects
    for insert with check (
        bucket_id = 'agst-files'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

drop policy if exists "fichiers_update_prefixe_client" on storage.objects;
create policy "fichiers_update_prefixe_client" on storage.objects
    for update using (
        bucket_id = 'agst-files'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

drop policy if exists "fichiers_delete_prefixe_client" on storage.objects;
create policy "fichiers_delete_prefixe_client" on storage.objects
    for delete using (
        bucket_id = 'agst-files'
        and (storage.foldername(name))[1] = auth.uid()::text
    );
