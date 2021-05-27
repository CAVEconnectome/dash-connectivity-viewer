import numpy as np
import seaborn as sns
import pandas as pd
import os

DEFAULT_DATASTACK = "minnie65_phase3_v1"
DEFAULT_SERVER_ADDRESS = "https://global.daf-apis.com"

TARGET_ROOT_ID_PER_CALL = 200
MAX_CHUNKS = 20

synapse_table = "synapses_pni_2"

dendrite_color = (0.894, 0.102, 0.110)
axon_color = (0.227, 0.459, 0.718)
clrs = np.array([axon_color, dendrite_color])

base_dir = os.path.dirname(__file__)
data_path = f"{base_dir}/data"

cell_type_table = "allen_soma_coarse_cell_class_model_v1"
ct_col = "cell_type"

own_soma_col = "own_soma_pt_position"

soma_depth_col = "soma_y_um"
valence_col = "is_inhib"
num_soma_col = "num_soma"
soma_position_col = "soma_pt_position"
soma_dist_col = "soma_distance_um"

syn_depth_col = "syn_y_um"
num_syn_col = "num_syn"
net_size_col = "net_syn_size"
mean_size_col = "mean_syn_size"

soma_table = "nucleus_neuron_svm"
soma_table_query = "cell_type == 'neuron'"

inhib_types = ["BC", "MC", "BPC", "NGC", "UnsI"]
exc_types = ["23P", "4P", "5P_IT", "5P_NP", "5P_PT", "6CT", "6IT", "UnsE"]
cat_dtype = pd.CategoricalDtype(categories=exc_types + inhib_types, ordered=True)

layer_bnds = np.load(f"{data_path}/layer_bounds_v1.npy")
height_bnds = np.load(f"{data_path}/height_bounds_v1.npy")
ticklocs = np.concatenate([height_bnds[0:1], layer_bnds, height_bnds[1:]])

e_colors = sns.color_palette("RdPu", n_colors=9)
i_colors = sns.color_palette("Greens", n_colors=9)

base_ind = 6
e_color = e_colors[base_ind]
i_color = i_colors[base_ind]

val_colors = np.array([e_color, i_color])

split_threshold = 0.7
voxel_resolution = np.array([4, 4, 40])

table_columns = [
    "pt_root_id",
    num_syn_col,
    net_size_col,
    mean_size_col,
    soma_dist_col,
    ct_col,
    soma_depth_col,
    valence_col,
    num_soma_col,
]