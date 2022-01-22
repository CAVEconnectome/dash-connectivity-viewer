from ..common.config import CommonConfig


class ConnectivityConfig(CommonConfig):
    def __init__(self, config):
        super().__init__(config)

        self.synapse_aggregation_rules = config.get("synapse_aggregation_rules", {})
        self.aggregation_columns = list(self.synapse_aggregation_rules.keys())
        self.table_columns = (
            [
                self.root_id_col,
                self.num_syn_col,
            ]
            + self.aggregation_columns
            + [self.num_soma_col]
        )
