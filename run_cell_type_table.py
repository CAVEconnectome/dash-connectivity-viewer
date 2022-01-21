from dash_connectivity_viewer.cell_type_table import create_app

config = {
    # "datastack": "minnie65_phase3_v1",
    "datastack": "flywire_fafb_production",
    "server_address": "https://global.daf-apis.com",
}

if __name__ == "__main__":
    app = create_app(config=config)
    app.run_server(port=8050)
