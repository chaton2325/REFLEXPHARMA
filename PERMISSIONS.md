# Système d'Autorisations - ReflexPharma

Ce document décrit le fonctionnement des droits d'accès au sein de l'application.

## Hiérarchie des Autorisations

Les accès sont déterminés selon une logique de priorité stricte :
1. **Autorisation Individuelle** : Si un droit est explicitement défini pour un utilisateur (Autorisé ou Refusé), c'est ce droit qui s'applique.
2. **Autorisation par Poste (Groupe)** : Si aucun droit n'est défini pour l'utilisateur, on vérifie les droits associés à son Poste (ex: Pharmacien, Préparateur).
3. **Rôle Superadmin** : Le superadmin conserve un accès total par défaut, sauf restriction explicite.

## Fonctionnalités gérées
- `gestion_employes` : Accès à la liste et modification des employés.
- `gestion_postes` : Accès à la configuration des types de postes.
- `gestion_fournisseurs` : Accès au CRUD des fournisseurs dans les paramètres.
- `consultation_salaires` : Accès à la visualisation des informations financières.

## Règles d'Affichage (UI/UX)
- Si un utilisateur n'a pas accès à une fonctionnalité, le bouton ou le menu correspondant **ne doit pas s'afficher** sur son tableau de bord ou dans la barre de navigation.
- Toute tentative d'accès direct via URL doit être bloquée par une redirection avec message d'erreur.
