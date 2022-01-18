import attrs
import numpy as np
import seaborn as sns
import pandas as pd
import os
import pathlib
from ..common.config import *

####################
### Column names ###
####################

cell_type_column = os.environ.get(
    "CT_CONN_CELL_TYPE_COLUMN",
    "cell_type",
)

soma_depth_column = os.environ.get("CT_CONN_SOMA_DEPTH_COLUMN", "soma_depth")
synapse_depth_column = os.environ.get("CT_CONN_SYN_DEPTH_COLUMN", "syn_depth")

is_inhibitory_column = os.environ.get("CT_CONN_IS_INHIBITORY_COLUMN", "is_inhibitory")

table_columns = [
    root_id_col,
    num_syn_col,
    net_size_col,
    mean_size_col,
    cell_type_column,
    soma_depth_column,
    is_inhibitory_column,
    f"{num_soma_col}_soma",
]

##########################################
### Layer data and spatial information ###
##########################################

base_dir = pathlib.Path(os.path.dirname(__file__))
data_path = base_dir.parent.joinpath("common/data")
layer_bnds = np.load(f"{data_path}/layer_bounds_v1.npy")
height_bnds = np.load(f"{data_path}/height_bounds_v1.npy")
ticklocs = np.concatenate([height_bnds[0:1], layer_bnds, height_bnds[1:]])

###########################
### Category parameters ###
###########################

allowed_cell_type_schema = os.environ.get(
    "CT_CONN_CELL_TYPE_SCHEMA", "cell_type_local"
).split(",")

########################
# Visualization Config #
########################
class VisConfig:
    def __init__(
        self,
        dendrite_color,
        axon_color,
        e_palette,
        i_palette,
        u_palette,
        base_ind=6,
        n_e_colors=9,
        n_i_colors=9,
        n_u_colors=9,
        e_string="Exc",
        i_string="Inh",
        u_string="Unknown",
        e_opacity=0.5,
        i_opacity=0.75,
        u_opacity=0.3,
    ):
        self.dendrite_color = dendrite_color
        self.axon_color = axon_color

        self.e_colors = sns.color_palette(e_palette, n_colors=n_e_colors)
        self.i_colors = sns.color_palette(i_palette, n_colors=n_i_colors)
        self.u_colors = sns.color_palette(u_palette, n_colors=n_u_colors)
        self.base_ind = base_ind

        self.e_string = e_string
        self.i_string = i_string
        self.u_string = u_string

        self.e_opacity = e_opacity
        self.i_opacity = i_opacity
        self.u_opacity = u_opacity

    @property
    def clrs(self):
        return np.array([self.axon_color, self.dendrite_color])

    @property
    def e_color(self):
        return self.e_colors[self.base_ind]

    @property
    def i_color(self):
        return self.i_colors[self.base_ind]

    @property
    def u_color(self):
        return self.u_colors[max(self.base_ind - 2, 0)]

    @property
    def valence_colors(self):
        return np.vstack([self.e_color, self.i_color, self.u_color])

    def valence_color_map(self, is_inhib):
        cmap = []
        for x in is_inhib:
            if pd.isna(x):
                cmap.append(2)
            elif x:
                cmap.append(0)
            else:
                cmap.append(1)
        return np.array(cmap)

    def valence_string_map(self, is_inhib):
        smap = []
        for x in is_inhib:
            if pd.isna(x):
                smap.append(self.u_string)
            elif x:
                smap.append(self.i_string)
            else:
                smap.append(self.e_string)
        return smap


dendrite_color = os.environ.get("CT_CONN_DENDRITE_COLOR")
if dendrite_color is None:
    dendrite_color = (0.894, 0.102, 0.110)
else:
    dendrite_color = parse_environ_vector(dendrite_color, float)

axon_color = os.environ.get("CT_CONN_AXON_COLOR")
if axon_color is None:
    axon_color = (0.227, 0.459, 0.718)
else:
    axon_color = parse_environ_vector(axon_color, float)

e_color_palette = os.environ.get("CT_CONN_E_PALETTE", "RdPu")
i_color_palette = os.environ.get("CT_CONN_I_PALETTE", "Greens")
u_color_palette = os.environ.get("CT_CONN_U_PALETTE", "Greys")
base_ind = int(os.environ.get("CT_CONN_PALETTE_BASE", 6))

vis_config = VisConfig(
    dendrite_color,
    axon_color,
    e_color_palette,
    i_color_palette,
    u_color_palette,
    base_ind,
)
