import plotly.graph_objects as go
from plotly.subplots import make_subplots
from .cortex_plots import *

bg_color = "White"
plotly_template = "plotly_white"

def bar_fig_df(df, config, color_column, width=450, height=350):
    bar = bar_plot_df(df, config, color_column)

    fig = go.Figure()
    fig.add_trace(bar)
        
    fig.update_layout(
        autosize=True,
        height=height,
        width=width,
        paper_bgcolor=bg_color,
        template=plotly_template,
        showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
    )

    return fig


def violin_fig(ndat, height=350, width=200):

    fig = go.Figure()

    violin_post = post_violin_plot(ndat)
    violin_pre = pre_violin_plot(ndat)
    fig.add_trace(violin_post)
    fig.add_trace(violin_pre)

    fig.update_layout(
        yaxis_title="Synapse Depth",
        height=height,
        width=width,
        paper_bgcolor=bg_color,
        template=plotly_template,
        showlegend=False,
        margin=dict(l=40, r=20, t=20, b=20),
    )

    fig.update_yaxes(
        tickvals=ndat.config.vis.ticklocs,
        ticktext=ndat.config.vis.tick_labels,
        ticklabelposition="outside bottom",
        range=ndat.config.height_bnds.astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
    )
    return fig

def scatter_fig_df(df, config, color_column, width=350, height=350):
    fig = go.Figure()
    scatter = synapse_soma_scatterplot(df, config, color_column)
    fig.add_traces(scatter)

    fig.update_layout(
        xaxis_title="Soma Depth",
        yaxis_title="Synapse Depth",
        height=height,
        width=width,
        paper_bgcolor=bg_color,
        template=plotly_template,
        showlegend=True,
        margin=dict(l=20, r=20, t=20, b=20),
    )

    fig.update_xaxes(
        tickvals=config.vis.ticklocs,
        ticktext=config.vis.tick_labels,
        ticklabelposition="outside right",
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="y",
    )

    fig.update_yaxes(
        tickvals=config.vis.ticklocs,
        ticktext=config.vis.tick_labels,
        ticklabelposition="outside bottom",
        range=config.height_bnds.astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="x",
        scaleratio=1,
    )
    return fig


def scatter_fig(ndat, color_column, width=350, height=350):

    fig = go.Figure()
    scatter = synapse_soma_scatterplot(
        ndat,
        ndat.config.synapse_depth_column,
        ndat.config.soma_depth_column,
        color_column,
    )
    fig.add_traces(scatter)

    fig.update_layout(
        xaxis_title="Soma Depth",
        yaxis_title="Synapse Depth",
        height=height,
        width=width,
        paper_bgcolor="White",
        template="plotly_white",
        showlegend=True,
        margin=dict(l=20, r=20, t=20, b=20),
    )

    fig.update_xaxes(
        tickvals=ndat.config.vis.ticklocs,
        ticktext=ndat.config.vis.tick_labels,
        ticklabelposition="outside right",
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="y",
    )

    fig.update_yaxes(
        tickvals=ndat.config.vis.ticklocs,
        ticktext=ndat.config.vis.tick_labels,
        ticklabelposition="outside bottom",
        range=ndat.config.height_bnds.astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="x",
        scaleratio=1,
    )
    return fig
