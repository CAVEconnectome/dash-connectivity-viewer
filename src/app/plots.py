import plotly.graph_objects as go
from plotly.subplots import make_subplots
from .config import ticklocs, height_bnds


def bar_fig(nrn_data, val_colors, height=350, width=450):

    bar_e = nrn_data.excitatory_bar_plot(val_colors[0])
    bar_i = nrn_data.inhib_bar_plot(val_colors[1])

    fig = make_subplots(rows=1, cols=2)
    fig.add_trace(bar_e, row=1, col=1)
    fig.update_yaxes(
        autorange="reversed",
    )

    fig.add_trace(bar_i, row=1, col=2)
    fig.update_yaxes(
        autorange="reversed",
    )

    fig.update_layout(
        autosize=True,
        height=height,
        width=width,
        paper_bgcolor="White",
        template="plotly_white",
        showlegend=False,
    )

    return fig


def violin_fig(
    nrn_data, axon_color, dendrite_color, ticklocs=ticklocs, height=350, width=200
):

    fig = go.Figure()

    violin_post = nrn_data.post_violin_plot(dendrite_color)
    violin_pre = nrn_data.pre_violin_plot(axon_color)
    fig.add_trace(violin_post)
    fig.add_trace(violin_pre)

    fig.update_layout(
        yaxis_title="Synapse Depth",
        height=height,
        width=width,
        paper_bgcolor="White",
        template="plotly_white",
        showlegend=False,
    )

    fig.update_yaxes(
        tickvals=ticklocs,
        ticktext=["L1", "L2/3", "L4", "L5", "L6", "WM", ""],
        ticklabelposition="outside bottom",
        range=height_bnds.astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
        automargin=True,
    )

    return fig


def scatter_fig(nrn_data, valence_colors, ticklocs=ticklocs, height=350):

    fig = go.Figure()
    scatter = nrn_data.synapse_soma_scatterplot(valence_colors)
    fig.add_trace(scatter)

    fig.update_layout(
        xaxis_title="Soma Depth",
        yaxis_title="Synapse Depth",
        height=height,
        width=height,
        paper_bgcolor="White",
        template="plotly_white",
        showlegend=False,
    )

    fig.update_xaxes(
        tickvals=ticklocs,
        ticktext=["L1", "L2/3", "L4", "L5", "L6", "WM", ""],
        ticklabelposition="outside right",
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="y",
    )

    fig.update_yaxes(
        tickvals=ticklocs,
        ticktext=["L1", "L2/3", "L4", "L5", "L6", "WM", ""],
        ticklabelposition="outside bottom",
        range=height_bnds.astype(int)[::-1].tolist(),
        gridcolor="#CCC",
        gridwidth=2,
    )

    return fig


def morpho_fig(
    nrn_data,
    axon_color,
    dendrite_color,
    valence_colors,
    ticklocs=ticklocs,
    height=350,
    width=600,
):

    fig = make_subplots(rows=1, cols=2, shared_yaxes=True)

    violin_post = nrn_data.post_violin_plot(dendrite_color)
    violin_pre = nrn_data.pre_violin_plot(axon_color)
    fig.add_trace(violin_post, row=1, col=1)
    fig.add_trace(violin_pre, row=1, col=1)

    scatter = nrn_data.synapse_soma_scatterplot(valence_colors)
    fig.add_trace(scatter, row=1, col=2)

    fig.update_xaxes(
        tickvals=ticklocs,
        ticktext=["L1", "L2/3", "L4", "L5", "L6", "WM", ""],
        ticklabelposition="outside right",
        gridcolor="#CCC",
        gridwidth=2,
        scaleanchor="y",
        row=1,
        col=2,
    )

    fig.update_yaxes(
        tickvals=ticklocs,
        ticktext=["L1", "L2/3", "L4", "L5", "L6", "WM", ""],
        ticklabelposition="outside bottom",
        autorange="reversed",
        gridcolor="#CCC",
        gridwidth=2,
        automargin=True,
    )

    fig.update_layout(
        autosize=True,
        height=height,
        width=width,
        paper_bgcolor="White",
        template="plotly_white",
        xaxis=dict(domain=[0, 0.3]),
        xaxis2=dict(domain=[0.45, 1]),
        showlegend=False,
    )
    return fig