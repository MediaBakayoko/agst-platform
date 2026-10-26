# Procedure de sauvegarde et restauration (mode fichiers locaux)

**STATUT ACTUEL : stockage 100% systeme de fichiers local**
(`platform/storage/<client_id>/<job_id>/`), aucune base de donnees
distante connectee. Cette procedure couvre ce mode -- a remplacer par
les sauvegardes automatiques Supabase une fois ce service connecte.

## Sauvegarde

```bash
# Depuis C:/Users/ASUS/projects/agst-platform/platform
tar -czf "backup_storage_$(date +%Y%m%d_%H%M%S).tar.gz" storage/
```
Copier l'archive generee vers un emplacement hors de la machine de
developpement (stockage externe, cloud prive) -- une sauvegarde
restant sur la meme machine ne protege pas contre une panne disque.

## Restauration

```bash
cd "C:/Users/ASUS/projects/agst-platform/platform"
tar -xzf backup_storage_YYYYMMDD_HHMMSS.tar.gz
```
Redemarrer le service apres restauration et verifier `/health` puis
qu'un job existant reste accessible via `GET /jobs/<job_id>` avec le
`X-Client-Id` d'origine.

## Limites de ce mode (a corriger avant un usage client reel)

- Aucune sauvegarde automatique planifiee -- entierement manuel pour
  l'instant.
- Aucune redondance -- une perte de disque = perte des donnees
  (projets, formulaires, registres d'alertes) tant que Supabase
  (avec sauvegardes automatiques integrees) n'est pas connecte.
- Recommandation : ne pas utiliser ce mode pour des donnees de projet
  reel/client payant avant la connexion Supabase -- le mode fichier
  local est pour le developpement/demonstration uniquement.

## Migrations (une fois Supabase connecte)

Les migrations SQL (`platform/supabase/migrations/`) sont
versionnees avec le code -- toute evolution de schema doit passer par
un nouveau fichier de migration numerote (`0002_...sql`), jamais une
modification manuelle directe du schema en production.
