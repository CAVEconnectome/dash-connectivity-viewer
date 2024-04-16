from dash_connectivity_viewer.cell_type_connectivity import create_app


minnie_config = {
    "cell_type_dropdown_options": [
        {
            "label": "All Soma Prediction",
            "value": "aibs_soma_nuc_metamodel_preds_v117",
        },
        {
            "label": "Column Census",
            "value": "minnie65_phase3_v1",
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
    "omit_cell_type_tables": ["nucleus_detection_v0", "nucleus_neuron_svm"],
    "default_cell_type_option": "aibs_soma_nuc_metamodel_preds_v117",
    "image_black": 0.35,
    "image_white": 0.7,
    "height_bounds": [0, 950],
    "layer_bounds": [106, 276, 411, 535, 768],
}

v1dd_config = {
    "datastack": "v1dd",
    "server_address": "https://globalv1.em.brain.allentech.org",
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
    "omit_cell_type_tables": ["nucleus_detection_v0"],
    "image_black": 0.35,
    "image_white": 0.7,
    "height_bounds": [-20, 900],
    "layer_bounds": [100, 270, 400, 550, 750],
}

flywire_config = {
    "datastack": "flywire_fafb_production",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "pre_pt",
    "ct_conn_show_depth_plots": False,
}


fanc_config = {
    "datastack": "fanc_production_mar2021",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "pre_pt",
    "ct_conn_show_depth_plots": False,
}

minnie_public_config = minnie_config.copy()
minnie_public_config["datastack"] = "minnie65_public"
minnie_public_config["disallow_live_query"] = True

if __name__ == "__main__":
    app = create_app(config=minnie_public_config)
    app.run_server(
        port=8050,
        debug=True,
    )
