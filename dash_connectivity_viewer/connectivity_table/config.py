DEFAULT_DATASTACK = "minnie65_phase3_v1"
DEFAULT_SERVER_ADDRESS = "https://global.daf-apis.com"
NUCLEUS_TABLE = "nucleus_neuron_svm"

synapse_table = "synapses_pni_2"

num_syn_col = "num_syn"
net_size_col = "net_syn_size"
mean_size_col = "mean_syn_size"

table_columns = [
    "root_id",
    num_syn_col,
    net_size_col,
    mean_size_col,
    # "ctr_pt_position",
]

hidden_columns = ["ctr_pt_position"]
# table_columns_with_point = table_columns + ["ctr_pt_position"]