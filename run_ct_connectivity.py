from dash_connectivity_viewer.cell_type_connectivity import create_app


minnie_config = {
    "cell_type_dropdown_options": [
        {
            "label": "All Soma Prediction",
            "value": "allen_soma_coarse_cell_class_model_v1",
        },
        {
            "label": "Column Census",
            "value": "allen_v1_column_types_slanted",
        },
    ],
    "datastack": "minnie65_phase3_v1",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "ctr_pt",
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
    "ct_conn_cell_type_schema": {
        "cell_type_local": None,
    },
    "omit_cell_type_tables": ["nucleus_neuron_svm"],
    "valence_map": {
        "allen_v1_column_types_slanted": {
            "column": "classification_system",
            "e": "aibs_coarse_excitatory",
            "i": "aibs_coarse_inhibitory",
        },
        "allen_soma_coarse_cell_class_model_v1": {
            "column": "classification_system",
            "e": "aibs_coarse_excitatory",
            "i": "aibs_coarse_inhibitory",
        },
    },
    "default_cell_type_option": "allen_soma_coarse_cell_class_model_v1",
    "image_black": 0.35,
    "image_white": 0.7,
}


flywire_config = {
    "datastack": "flywire_fafb_production",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "pre_pt",
    "ct_conn_cell_type_schema": {
        "cell_type_local": None,
    },
    "ct_conn_show_depth_plots": False,
}


fanc_config = {
    "datastack": "fanc_production_mar2021",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "pre_pt",
    "ct_conn_cell_type_schema": {
        "cell_type_local": None,
    },
    "ct_conn_show_depth_plots": False,
}

if __name__ == "__main__":
    app = create_app(config=flywire_config)
    app.run_server(port=8050)
