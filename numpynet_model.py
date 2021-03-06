"""
NumpyNet!

@author: Brad Beechler (brad.e.beechler@gmail.com)
"""
import math
import numpy as np
import numpynet_common as common
import numpynet_visualize as nnviz
from loggit import log


class NumpyNet:
    layer = []   # Also called neurons
    weight = []  # Also calles synapses
    num_layers = 0

    def __init__(self, num_features, batch_size, num_hidden=0, hidden_sizes=None,
                 activation="sigmoid", learning_rate=0.01,
                 learning_decay=None, weight_decay=None, dropout_rate=None,
                 init_weight_spread=1.0, random_seed=None):
        """
        Initialize a blank numpy net object
        This object will have input/output layers and weights (neurons and synapses)
        Both will be lists of numpy arrays having varying sizes
        Synapses are initialized with random weights with mean 0
        :param input_shape: Shape of the input layer
        :param output_shape: Shape of the output layer
        :param num_hidden: number of hidden layers
        :return:
        """
        # Set network hyperparameters
        self.activation_function = common.Activation(activation).function
        self.learning_rate = learning_rate
        self.learning_decay = learning_decay
        self.weight_decay = weight_decay
        self.dropout_rate = dropout_rate

        # Initialize arrays used for neurons and synapses
        self.batch_size = batch_size
        self.num_layers = 2 + num_hidden  # Input, output, and hidden layers
        self.num_hidden = num_hidden
        self.layer = [np.empty(0)] * self.num_layers
        self.weight = [np.empty(0)] * (self.num_layers - 1)

        # For diagnostics
        self.loss_history = list()
        self.predict_space = None  # If left undefined will define by training input bounds
        self.input_shape = [batch_size, num_features]
        if hidden_sizes is None:
            self.hidden_sizes = [batch_size] * self.num_hidden
        else:
            self.hidden_sizes = hidden_sizes
        self.output_shape = [batch_size, 1]

        # If requested seed random numbers to make calculation (makes repeatable)
        if random_seed is not None:
            np.random.seed(random_seed)
        else:
            current_seed = int(np.random.random(1) * 4.0E9)  # 4 billion is close to limit of 32 bit unsigned int
            np.random.seed(current_seed)
            log.out.info("No random seed selected, using: " + str(current_seed))

        # Initialize weights with random noise centered around zero, spread set by init_weight_spread
        self.weight[0] = (init_weight_spread * 2) * np.random.random([self.input_shape[1], self.hidden_sizes[0]]) - init_weight_spread
        for i in range(self.num_hidden-1):
            self.weight[i+1] = (init_weight_spread * 2) * np.random.random([self.weight[i].shape[1], self.hidden_sizes[i+1]]) - init_weight_spread
        self.weight[self.num_hidden] = (init_weight_spread * 2) * np.random.random([self.weight[self.num_hidden-1].shape[1], self.output_shape[1]]) - init_weight_spread

        # Initialize layers with zeros
        self.forward(np.zeros(self.input_shape))

    def forward(self, input_info):
        # Feed forward through layers
        self.layer[0] = input_info
        for i in range(self.num_layers - 1):
            self.layer[i + 1] = self.activation_function(np.dot(self.layer[i], self.weight[i]))

    def predict(self, input_info):
        # Feed forward through layers not saving result in network and return the result
        prediction = input_info
        for i in range(self.num_layers - 1):
            prediction = self.activation_function(np.dot(prediction, self.weight[i]))
        return prediction

    def train(self, train_in, train_out, epochs=100,
              visualize=True, visualize_percent=5, debug_visualize=True):
        set_size = train_in.shape[0]
        log.out.info("Given " + str(set_size) + " training points.")
        iterations = math.ceil(set_size / self.batch_size)
        log.out.info("Will train in " + str(iterations) + " iterations per epoch for " + str(epochs) +
                     " epochs. (In batches of " + str(self.batch_size) + ")")
        runfracround = round(epochs * (0.01 * visualize_percent))
        log.out.info("Will output every " + str(runfracround) + " epochs.")
        # Set prediction space (for diagnostics)
        if self.predict_space is None:
            self.predict_space = [np.min(train_in[:, 0]), np.max(train_in[:, 0]),
                                  np.min(train_in[:, 1]), np.max(train_in[:, 1])]
        # Set error matrix
        error = [None] * len(self.layer)
        delta = [None] * len(self.layer)

        # Epoch training loop (each epoch goes over entire data set once)
        for e, epoch in enumerate(range(epochs)):
            # Reset the available data indices
            available_indexes = np.arange(set_size)
            # Loop over the batches of data for this epoch
            batch_loss = list()
            for t in range(iterations):
                # Get random data for this batch
                if available_indexes.size < self.batch_size:
                    add_randoms = np.random.randint(set_size, size=self.batch_size-available_indexes.size)
                    available_indexes = np.concatenate((available_indexes, add_randoms))
                # TODO: try grid sampling instead of random
                batch_indexes = np.random.choice(available_indexes, self.batch_size, replace=False)
                batch_in = train_in[batch_indexes, :]
                batch_out = train_out[batch_indexes, :]
                # Remove these indices from the available pool
                available_indexes = available_indexes[~np.in1d(available_indexes, batch_indexes).reshape(available_indexes.shape)]

                # Run the network forward with the current weights
                self.forward(batch_in)

                # Propagate backwards through the layers and calculate error
                # Start with the output layer
                layer_index = self.num_layers - 1
                error[layer_index] = batch_out - self.layer[layer_index]
                # Find the direction of the target value and move towards it depending on confidence
                delta[layer_index] = (self.learning_rate * error[layer_index] *
                                      self.activation_function(self.layer[layer_index], deriv=True))

                # Work backwards through the hidden layers
                for layer_index in range(len(self.layer) - 2, 0, -1):
                    error[layer_index] = delta[layer_index + 1].dot(self.weight[layer_index].T)
                    # Find the direction of the target value and move towards it depending on confidence
                    delta[layer_index] = error[layer_index] * self.activation_function(self.layer[layer_index], deriv=True)

                # Update the weights using the deltas we just found
                for layer_index in range(len(self.layer) - 1, 0, -1):
                    self.weight[layer_index - 1] += self.layer[layer_index - 1].T.dot(delta[layer_index])

                batch_loss.append(np.sum(np.abs(error[-1])))

            self.loss_history.append(sum(batch_loss) / (iterations * len(train_in)))

            # Report error every x% and output visualization
            if (e % runfracround) == 0:
                log.out.info("Epoch: " + str(e) + " Average Error: " + str(self.loss_history[-1]))
                if visualize:
                    nnviz.plot_loss(self.loss_history, rolling_size=runfracround)
                    prediction_matrix, axis_x, axis_y = common.predict_2d_space(self, delta=0.02)
                    nnviz.plot_2d_prediction(prediction_matrix, axis_x, axis_y)
                    if debug_visualize:
                        nnviz.plot_network(self.layer, self.weight)

            if self.weight_decay is not None:
                for layer_index in range(len(self.layer) - 1, 0, -1):
                    self.weight[layer_index - 1] -= self.weight[layer_index - 1] * self.learning_rate * self.weight_decay
            #TODO visualize weight growth, should this be by epoch or every?

            # if self.dropout_rate is not None:


        log.out.info("Final Error: " + str(np.mean(np.abs(error[-1]))))
        prediction_matrix, axis_x, axis_y = common.predict_2d_space(self, delta=0.002)
        if visualize:
            nnviz.plot_2d_prediction(prediction_matrix, axis_x, axis_y, title="Final Prediction")

    def report_model(self):
        log.out.info("Model topology: ")
        log.out.info("Number of layers: " + str(self.num_layers) + " (" + str(self.num_layers - 2) + " hidden)")
        for l in range(self.num_layers-1):
            log.out.info("Layer " + str(l+1) + ": " + str(self.layer[l].shape))
            log.out.info("Weight " + str(l+1) + ": " + str(self.weight[l].shape))
        log.out.info("Layer " + str(self.num_layers+1) + ": " + str(self.layer[-1].shape))

        # import objgraph
        # objgraph.show_refs([self.__dict__], filename='./nn-graph.png')
