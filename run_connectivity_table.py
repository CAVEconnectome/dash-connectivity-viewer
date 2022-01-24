from dash_connectivity_viewer.connectivity_table import create_app


minnie_config = {
    "datastack": "minnie65_phase3_v1",
    "server_address": "https://global.daf-apis.com",
    "syn_position_column": "ctr_pt",
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
    "nucleus_table": "nuclei_aug2021ver2",
}

if __name__ == "__main__":
    app = create_app(config=fanc_config)
    app.run_server(port=8050)
