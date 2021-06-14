from dash_viewer.connectivity_table import create_app

if __name__ == "__main__":
    app = create_app()
    app.run_server(port=8050)
