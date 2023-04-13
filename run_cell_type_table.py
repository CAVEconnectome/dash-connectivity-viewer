from dash_connectivity_viewer.cell_type_table import create_app

minnie_config = {
    "datastack": "minnie65_phase3_v1",
    "server_address": "https://global.daf-apis.com",
    "ct_cell_type_schema": {
        "cell_type_local": None,
    },
    "image_black": 0.35,
    "image_white": 0.7,
}

v1dd_config = {
    "datastack": "v1dd",
    "server_address": "https://globalv1.em.brain.allentech.org",
    "image_black": 0.35,
    "image_white": 0.7,
}

flywire_config = {
    "datastack": "flywire_fafb_production",
    "server_address": "https://global.daf-apis.com",
    "ct_cell_type_schema": {
        "cell_type_local": None,
    },
}

fanc_config = {
    "datastack": "fanc_production_mar2021",
    "server_address": "https://global.daf-apis.com",
    "ct_cell_type_schema": {
        "cell_type_local": None,
    },
}

if __name__ == "__main__":
    app = create_app(config=v1dd_config)
    app.run_server(
        port=8050,
        )
