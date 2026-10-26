# Notifications -- prerequis (architecture preparee, non connectee)

**STATUT : aucun fournisseur de notification n'est configure.**
Aucun message n'a jamais ete envoye par ce systeme -- ne jamais
pretendre qu'une alerte a ete notifiee sans confirmation reelle du
fournisseur.

## Architecture prevue (extensible)

Une notification = evenement (nouvelle alerte critique, synchro en
echec, formulaire approuve) -> canal(aux) configure(s) -> enregistrement
du statut d'envoi (succes/echec) en base.

### Canal "dans l'application" (toujours disponible, pas de prerequis)
Le registre d'alertes (`registre_alertes.csv/.xlsx` ou, une fois
Supabase connecte, la table `anomalies`) est deja consultable --
c'est le mecanisme de notification minimal garanti, sans dependance
externe.

### Canal email (necessite un fournisseur)
Prerequis avant implementation :
1. Un compte sur un fournisseur SMTP transactionnel (ex: Resend,
   SendGrid, Mailgun, ou SMTP direct via un compte Gmail
   applicatif -- **distinct** du compte Gmail personnel deja utilise
   pour MediaJobSearcher, pour ne pas melanger les deux usages).
2. Cle API ou credentials SMTP, stockes cote serveur uniquement
   (variable d'environnement, jamais en dur, jamais dans le frontend).
3. Decision metier : qui recoit quoi (superviseur du projet ? liste
   de diffusion ?) -- a definir avec l'utilisateur avant codage.

Contenu minimal d'une notification (jamais de donnee personnelle de
beneficiaire) : projet, reference de soumission (id technique, pas le
nom du repondant), type de probleme, gravite, lien securise vers
l'interface de traitement (jamais le detail de l'anomalie en clair
dans un email qui pourrait etre transfere sans controle d'acces).

### Canal SMS / autre
Non envisage tant qu'aucun fournisseur n'est explicitement choisi et
autorise par l'utilisateur -- cout et complexite reglementaire
(consentement) plus eleves que l'email.

## Ce qui bloque l'implementation aujourd'hui
Aucun fournisseur email choisi. Decision a prendre avec l'utilisateur :
quel fournisseur, quel budget (certains ont un plan gratuit limite),
quelle liste de destinataires par defaut.
