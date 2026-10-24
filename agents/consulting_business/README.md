# Consulting & Business Agent

Accélère la préparation, l'organisation et le suivi des missions de
conseil, formation et expertise géospatiale d'AGST : analyse des termes
de référence (ToR), préparation d'offres techniques et financières,
budgets, chronogrammes, suivi des échéances et comptes rendus.

## Principes (non négociables)

- **Jamais d'invention** : aucune expérience, référence client,
  qualification, tarif accepté ou donnée financière n'est inventée. Tout
  ce qui apparaît dans une offre vient d'un fichier de références réel
  fourni par l'utilisateur (`sample_data/profil_consultant.json` — à
  remplacer par les vraies données).
- **Hypothèses vs validé** : tout montant budgétaire est marqué
  `[HYPOTHESE]` tant qu'il n'a pas été confirmé explicitement par
  l'utilisateur ; jamais présenté comme un tarif déjà accepté.
- **Aucun envoi/signature/paiement automatique.** L'agent prépare des
  brouillons ; l'envoi d'une offre ou l'acceptation contractuelle
  nécessite une validation humaine explicite à chaque fois.
- **Confidentialité** : les documents contractuels ne sont jamais
  exposés hors du dossier de sortie dédié au projet.

## Modules

1. **`tor_analyzer.py`** — extrait d'un ToR (texte/Word) les éléments
   structurants : objectifs, livrables attendus, échéances, budget
   plafond (si mentionné), qualifications requises. Signale
   explicitement toute section non trouvée plutôt que de deviner.
2. **`budget_builder.py`** — construit un budget détaillé (Excel) à
   partir de lignes fournies par l'utilisateur (postes, quantités, taux
   journaliers) — ne propose jamais de taux par défaut inventé.
3. **`proposal_builder.py`** — génère un brouillon d'offre technique
   (Word) à partir du ToR analysé + du profil réel du consultant/cabinet.
4. **`opportunity_tracker.py`** — registre des opportunités (CSV/Excel) :
   statut, échéance, montant, probabilité — pour le suivi.

## Usage

```bash
# 1. Analyser un ToR
python scripts/tor_analyzer.py sample_data/tor_test.txt --output-dir output/

# 2. Construire un budget (lignes fournies dans un CSV)
python scripts/budget_builder.py sample_data/lignes_budget_test.csv --output-dir output/

# 3. Générer un brouillon d'offre technique
python scripts/proposal_builder.py \
    --tor-analysis output/tor_test_*/tor_analysis.json \
    --profile sample_data/profil_consultant.json \
    --output-dir output/

# 4. Mettre à jour le registre des opportunités
python scripts/opportunity_tracker.py add \
    --registry sample_data/registre_opportunites.csv \
    --client "Nom client" --titre "Intitulé mission" \
    --echeance 2026-12-01 --montant-hypothese 0 --statut "a_preparer"
```

## Limites assumées

- L'extraction des ToR est basée sur des mots-clés/sections usuelles
  (objectifs, livrables, délais, budget, qualifications) — un ToR
  atypique peut nécessiter une relecture manuelle ; l'agent signale
  toujours les sections non détectées plutôt que d'inventer leur contenu.
