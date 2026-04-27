FEATURES = {
    'gestion_employes': 'Gérer les employés',
    'gestion_postes': 'Gérer les postes',
    'gestion_fournisseurs': 'Gérer les fournisseurs',
    'gestion_groupes_fournisseurs': 'Gérer les groupes de fournisseurs'
}

def get_feature_label(feature):
    return FEATURES.get(feature, feature)
