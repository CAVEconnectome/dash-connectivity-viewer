from dash_connectivity_viewer.connectivity_table import create_app

config = {
    "datastack": "minnie65_phase3_v1",
    "server_address": "https://global.daf-apis.com",
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
}

if __name__ == "__main__":
    app = create_app(config=config)
    app.run_server(port=8050)
