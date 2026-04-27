FEATURES = {
    'gestion_employes': 'Gérer les employés',
    'gestion_postes': 'Gérer les postes',
    'gestion_fournisseurs': 'Gérer les fournisseurs',
    'gestion_groupes_fournisseurs': 'Gérer les groupes de fournisseurs',
    'gestion_rayons': 'Gérer les rayons',
    'gestion_familles': 'Gérer les familles',
    'gestion_sections': 'Gérer les sections',
    'gestion_produits': 'Gérer les produits'
}

def get_feature_label(feature):
    return FEATURES.get(feature, feature)
