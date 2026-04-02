let
    // Source PostgreSQL
    Source = try

        let

            _src = PostgreSQL.Database("db.entreprise.fr:5432", "ventes_db"),

            _nav = _src{[Schema="public", Item="Produits"]}[Data]

        in _nav

    otherwise

        #table({"produit_id", "nom_produit", "categorie", "sous_categorie", "marque", "cout_achat"}, {}),
    #"Renamed Columns" = Table.RenameColumns(Source, {{"produit_id", "ID Produit"}, {"nom_produit", "Nom du Produit"}, {"categorie", "Catégorie"}, {"sous_categorie", "Sous-Catégorie"}, {"marque", "Marque"}, {"cout_achat", "Coût d'Achat"}}),
    Result = #"Renamed Columns"
in
    Result