from dash_connectivity_viewer.cell_type_table import create_app

minnie_config = {
    "datastack": "minnie65_phase3_v1`",
    "server_address": "https://global.daf-apis.com",
}

flywire_config = {
    "datastack": "flywire_fafb_production",
    "server_address": "https://global.daf-apis.com",
}

fanc_config = {
    "datastack": "fanc_production_mar2021",
    "server_address": "https://global.daf-apis.com",
}

if __name__ == "__main__":
    app = create_app(config=minnie_config)
    app.run_server(port=8050)
