from .config import *
import plotly.graph_objects as go


def _violin_plot(syn_df, x_col, y_col, name, side, color, xaxis, yaxis):
    return go.Violin(
        x=syn_df[x_col],
        y=syn_df[y_col],
        side=side,
        scalegroup="syn",
        name=name,
        points=False,
        line_color=f"rgb{color}",
        fillcolor=f"rgb{color}",
        xaxis=xaxis,
        yaxis=yaxis,
    )


def post_violin_plot(
    ndat,
    xaxis=None,
    yaxis=None,
):
    return _violin_plot(
        ndat.syn_all_df().query('direction == "post"'),
        x_col="x",
        y_col=ndat.syn_depth_col,
        name="Post",
        side="negative",
        color=vis_config.dendrite_color,
        xaxis=xaxis,
        yaxis=yaxis,
    )


def pre_violin_plot(
    ndat,
    xaxis=None,
    yaxis=None,
):
    return _violin_plot(
        ndat.syn_all_df().query('direction == "pre"'),
        x_col="x",
        y_col=ndat.syn_depth_col,
        name="Pre",
        side="positive",
        color=vis_config.axon_color,
        xaxis=xaxis,
        yaxis=yaxis,
    )


def synapse_soma_scatterplot(
    ndat,
    syn_depth_column,
    soma_depth_column,
    is_inhibitory_column=None,
    xaxis=None,
    yaxis=None,
):
    drop_columns = [syn_depth_column, soma_depth_column]
    targ_df = ndat.partners_out().dropna(subset=drop_columns)

    if len(targ_df) > 0:
        color_vec = targ_df[is_inhibitory_column].astype(int)
    else:
        color_vec = 0

    return go.ScatterGl(
        x=targ_df[soma_depth_column],
        y=targ_df[syn_depth_column],
        mode="markers",
        marker=dict(
            color=vis_config.valence_colors[color_vec],
            line_width=0,
            size=5,
            opacity=0.5,
        ),
        xaxis=xaxis,
        yaxis=yaxis,
    )


def bar_data(
    ndat,
    cell_type_column,
):
    targ_df = ndat.partners_out().dropna(subset=[cell_type_column])
    return targ_df.groupby(cell_type_column)[num_syn_col].sum()


def _bar_plot(
    bar_data,
    name,
    color,
):
    return go.Bar(
        name=name,
        x=bar_data.values,
        y=bar_data.index,
        marker_color=f"rgb{color}",
        orientation="h",
    )

def _format_color(color):
    return tuple(np.floor(255 * color).astype(int)

def excitatory_bar_plot(
    ndat,
    color,
    is_inhibitory_column=None,
    cell_types=None,
):
    