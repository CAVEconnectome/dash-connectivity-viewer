from dash_connectivity_viewer.cell_type_connectivity import create_app

config = {
    "cell_type_dropdown_options": [
        {
            "label": "All Soma Prediction",
            "value": "allen_soma_coarse_cell_class_model_v1",
        },
        {
            "label": "Column Census (slanted)",
            "value": "allen_v1_column_types_slanted",
        },
        {
            "label": "Column Census (straight)",
            "value": "allen_v1_column_types_v2",
        },
        {
            "label": "Thalamic Axons",
            "value": "allen_v1_column_thalamic",
        },
        {
            "label": "Layer 5 IT PyC Subtypes",
            "value": "allen_column_l5it_types",
        },
        {
            "label": "Basket Subtypes",
            "value": "allen_column_basket_molecular",
        },
    ],
    "omit_cell_type_tables": ["nucleus_neuron_svm"],
    "valence_map_table": {
        "allen_v1_column_types_slanted": [
            "classification_system",
            "aibs_coarse_excitatory",
            "aibs_coarse_inhibitory",
        ],
        "allen_soma_coarse_cell_class_model_v1": [
            "classification_system",
            "aibs_coarse_excitatory",
            "aibs_coarse_inhibitory",
        ],
    },
    "cell_type_column_schema_lookup": {
        "cell_type_local": "cell_type",
    },
}

if __name__ == "__main__":
    app = create_app(config=config)
    app.run_server(port=8050)
