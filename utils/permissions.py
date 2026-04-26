FEATURES = {
    'gestion_employes': 'Gérer les employés',
    'gestion_postes': 'Gérer les postes'
}

def get_feature_label(feature):
    return FEATURES.get(feature, feature)
