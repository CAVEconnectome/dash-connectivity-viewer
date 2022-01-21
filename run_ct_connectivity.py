from dash_connectivity_viewer.cell_type_connectivity import create_app

config = {
    "cell_type_dropdown_options": [
        {
            "label": "All Soma Prediction",
            "value": "allen_soma_coarse_cell_class_model_v1",
        },
        {
            "label": "Column Census",
            "value": "allen_v1_column_types_slanted",
        },
        {
            "label": "Column Thalamic Axons",
            "value": "allen_v1_column_thalamic",
        },
        {
            "label": "Column Basket Subtypes",
            "value": "allen_column_basket_molecular",
        },
    ],
    "datastack": "minnie65_phase3_v1",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "pre_pt",
    "synapse_aggregation_rules": {
        "mean_size": {
            "column": "size",
            "agg": "mean",
        },
        "net_size": {
            "column": "size",
            "agg": "sum",
        },
    },
    "cell_type_column_schema_lookup": {
        "cell_type_local": "cell_type",
    },
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
    "default_cell_type_dropdown": "allen_soma_coarse_cell_class_model_v1",
}

if __name__ == "__main__":
    app = create_app(config=config)
    app.run_server(port=8050, debug=True)
