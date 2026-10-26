-- AGST Platform -- Schema Supabase pour Survey Intelligence
-- STATUT : PREPARE MAIS NON APPLIQUE -- aucun projet Supabase connecte
-- a ce jour. A executer via `supabase db push` ou le SQL Editor du
-- dashboard Supabase UNE FOIS le projet cree et SUPABASE_URL/
-- SUPABASE_ANON_KEY/SUPABASE_JWT_SECRET configures cote serveur.
--
-- Principes de securite appliques (RLS) :
-- - Isolation stricte par organisation (org_id) ET par utilisateur
--   authentifie (auth.uid()) -- un client ne peut jamais lire/modifier
--   les lignes d'une autre organisation, meme en changeant un
--   identifiant dans la requete (verifie par policy, pas par le
--   frontend).
-- - La cle service_role n'est JAMAIS utilisee cote frontend -- RLS
--   s'applique a toute requete authentifiee avec la cle anon.

create extension if not exists "pgcrypto";

-- ============================================================
-- Organisations (isolation multi-client au niveau le plus haut)
-- ============================================================
create table if not exists organisations (
    id uuid primary key default gen_random_uuid(),
    nom text not null,
    cree_le timestamptz not null default now()
);

-- Table de liaison utilisateur <-> organisation (role simple)
create table if not exists membres_organisation (
    id uuid primary key default gen_random_uuid(),
    organisation_id uuid not null references organisations(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null default 'membre' check (role in ('admin', 'superviseur', 'membre')),
    cree_le timestamptz not null default now(),
    unique (organisation_id, user_id)
);

-- ============================================================
-- Projets
-- ============================================================
create table if not exists projets (
    id uuid primary key default gen_random_uuid(),
    organisation_id uuid not null references organisations(id) on delete cascade,
    nom text not null,
    description_source text,            -- texte libre fourni par l'utilisateur
    elements_structures jsonb,          -- sortie de project_intake.py
    elements_non_detectes jsonb,        -- liste des elements manquants signales
    statut text not null default 'en_conception' check (
        statut in ('en_conception', 'indicateurs_approuves', 'formulaire_approuve', 'collecte_active', 'clos')
    ),
    cree_par uuid references auth.users(id),
    cree_le timestamptz not null default now(),
    maj_le timestamptz not null default now()
);

-- ============================================================
-- Indicateurs (une ligne par indicateur de la matrice)
-- ============================================================
create table if not exists indicateurs (
    id uuid primary key default gen_random_uuid(),
    projet_id uuid not null references projets(id) on delete cascade,
    objectif text,
    resultat_associe text,
    intitule text not null,
    type_indicateur text check (type_indicateur in ('realisation', 'resultat', 'impact') or type_indicateur is null),
    definition text,
    formule text,
    numerateur text,
    denominateur text,
    unite text,
    valeur_reference text,              -- texte libre : jamais calcule/invente automatiquement
    cible text,                         -- idem -- arbitrage humain requis, jamais devine
    source_verification text,
    methode_collecte text,
    frequence text,
    desagregation text,
    question_necessaire text,
    regle_qualite text,
    limites_methodologiques text,
    statut_validation text not null default 'propose' check (statut_validation in ('propose', 'approuve', 'rejete')),
    cree_le timestamptz not null default now(),
    maj_le timestamptz not null default now()
);

-- ============================================================
-- Versions de formulaire XLSForm (traçabilite, jamais d'ecrasement)
-- ============================================================
create table if not exists formulaires (
    id uuid primary key default gen_random_uuid(),
    projet_id uuid not null references projets(id) on delete cascade,
    version integer not null,
    titre text not null,
    stockage_path text not null,        -- chemin/cle du .xlsx dans Supabase Storage
    statut_validation_technique text not null default 'non_valide' check (
        statut_validation_technique in ('non_valide', 'valide', 'invalide')
    ),
    erreurs_validation jsonb,
    approuve_par uuid references auth.users(id),
    approuve_le timestamptz,
    deploye boolean not null default false,
    kobo_asset_uid text,                -- identifiant Kobo une fois deploye
    kobo_deployment_link text,
    cree_le timestamptz not null default now(),
    unique (projet_id, version)
);

-- ============================================================
-- Soumissions (cache local des soumissions Kobo, ou import manuel)
-- ============================================================
create table if not exists soumissions (
    id uuid primary key default gen_random_uuid(),
    projet_id uuid not null references projets(id) on delete cascade,
    formulaire_id uuid references formulaires(id),
    kobo_submission_uuid text,          -- identifiant Kobo si collecte reelle
    donnees jsonb not null,
    hash_contenu text not null,         -- pour detecter les modifications (idempotence)
    enqueteur text,
    recue_le timestamptz not null default now(),
    derniere_analyse_le timestamptz,
    unique (projet_id, kobo_submission_uuid)
);

-- ============================================================
-- Anomalies / registre d'alertes
-- ============================================================
create table if not exists anomalies (
    id uuid primary key default gen_random_uuid(),
    projet_id uuid not null references projets(id) on delete cascade,
    soumission_id uuid references soumissions(id) on delete cascade,
    regle_declenchee text not null,
    valeur_concernee text,
    niveau_gravite text not null check (niveau_gravite in ('erreur_bloquante', 'anomalie_probable', 'valeur_inhabituelle')),
    justification text not null,
    indicateur_potentiellement_affecte text,
    action_recommandee text,
    responsable_verification uuid references auth.users(id),
    statut_resolution text not null default 'nouvelle' check (
        statut_resolution in ('nouvelle', 'a_verifier', 'correction_demandee', 'corrigee', 'cloturee', 'faux_positif')
    ),
    historique_corrections jsonb not null default '[]'::jsonb,
    detectee_le timestamptz not null default now()
);

-- ============================================================
-- Historique de synchronisation Kobo (suivi des executions)
-- ============================================================
create table if not exists synchronisations (
    id uuid primary key default gen_random_uuid(),
    projet_id uuid not null references projets(id) on delete cascade,
    demarree_le timestamptz not null default now(),
    terminee_le timestamptz,
    statut text not null default 'en_cours' check (statut in ('en_cours', 'succes', 'echec')),
    n_soumissions_recuperees integer,
    n_soumissions_nouvelles integer,
    n_soumissions_modifiees integer,
    erreur text
);

-- ============================================================
-- RLS -- active sur toutes les tables sensibles
-- ============================================================
alter table organisations enable row level security;
alter table membres_organisation enable row level security;
alter table projets enable row level security;
alter table indicateurs enable row level security;
alter table formulaires enable row level security;
alter table soumissions enable row level security;
alter table anomalies enable row level security;
alter table synchronisations enable row level security;

-- Un utilisateur ne voit que les organisations dont il est membre.
create policy org_select on organisations for select
    using (id in (select organisation_id from membres_organisation where user_id = auth.uid()));

create policy membres_select on membres_organisation for select
    using (organisation_id in (select organisation_id from membres_organisation where user_id = auth.uid()));

-- Toutes les tables projet-dependantes : isolation via la chaine
-- projet -> organisation -> membres_organisation -> auth.uid().
create policy projets_isolation on projets for all
    using (organisation_id in (select organisation_id from membres_organisation where user_id = auth.uid()))
    with check (organisation_id in (select organisation_id from membres_organisation where user_id = auth.uid()));

create policy indicateurs_isolation on indicateurs for all
    using (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ))
    with check (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ));

create policy formulaires_isolation on formulaires for all
    using (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ))
    with check (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ));

create policy soumissions_isolation on soumissions for all
    using (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ))
    with check (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ));

create policy anomalies_isolation on anomalies for all
    using (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ))
    with check (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ));

create policy synchronisations_isolation on synchronisations for all
    using (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ))
    with check (projet_id in (
        select p.id from projets p
        join membres_organisation m on m.organisation_id = p.organisation_id
        where m.user_id = auth.uid()
    ));

-- Index utiles
create index if not exists idx_projets_org on projets(organisation_id);
create index if not exists idx_indicateurs_projet on indicateurs(projet_id);
create index if not exists idx_soumissions_projet on soumissions(projet_id);
create index if not exists idx_anomalies_projet on anomalies(projet_id);
create index if not exists idx_anomalies_gravite on anomalies(niveau_gravite);
create index if not exists idx_anomalies_statut on anomalies(statut_resolution);
