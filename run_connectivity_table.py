from dash_connectivity_viewer.connectivity_table import create_app


minnie_config = {
    "datastack": "minnie65_phase3_v1",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "ctr_pt",
    "image_black": 0.35,
    "image_white": 0.7,
}

minnie_public_config = {
    "datastack": "minnie65_public",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "ctr_pt",
    "image_black": 0.35,
    "image_white": 0.7,
    "disallow_live_query": True,
}

v1dd_config = {
    "datastack": "v1dd",
    "syn_position_column": "ctr_pt",
    "server_address": "https://globalv1.em.brain.allentech.org",
    "image_black": 0.35,
    "image_white": 0.7,
}

flywire_config = {
    "datastack": "flywire_fafb_production",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "pre_pt",
}

fanc_config = {
    "datastack": "fanc_production_mar2021",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "pre_pt",
}

if __name__ == "__main__":
    app = create_app(config=minnie_public_config)
    app.run_server(port=8050, debug=True)
