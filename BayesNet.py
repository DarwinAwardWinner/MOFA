from __future__ import division
import numpy.linalg as linalg
from time import time
import os
import scipy as s
import cPickle as pkl
import pandas as pd

from nodes import Node
from variational_nodes import Unobserved_Variational_Node, Variational_Node
from utils import corr

"""
This module is used to define the class containing the entire Bayesian Network, 
and the corresponding attributes/methods to train the model, set algorithmic options, calculate lower bound, etc.

A Bayesian network requires the following information:
- Keyworded dimensionalities (N=10, D=100, ...)
- Nodes: instances (or children) of 'Node' class.
    right now we have implemented two types of nodes: variational and local
- Update schedule: order of nodes in the updates
- Monitoring and algorithmic options: verbosity, tolerance for convergence, number of iterations, lower bound frequency...

To-do:
- More sanity checks (algorithmic options)
- assert nodes and options and so on is dic
"""

class BayesNet(object):

    # def __init__(self, dim={}, nodes={}, schedule=(), options={}, trial=1):
    def __init__(self, dim, nodes, schedule, options, trial=1):
        #  dim: dictionary with the dimensions and its keynames, ex. {'N'=10, 'M'=3, ...}
        #  nodes: dictionary with all nodes where the keys are the name of the node and the values are instances of Variational_Node() or Multiview_Variational_Node() 
        #  schedule: tuple with the names of the nodes to be updated in the given order. Nodes not present in schedule will not be updated
        # print schedule
        # print nodes
        assert len(schedule) == len(nodes), "Different number of nodes and schedules provided"

        self.dim = dim
        self.nodes = nodes
        self.schedule = schedule
        self.options = options
        self.trial = trial

        # If schedule not provided, set it to the provided order of the nodes (use OrderedDict to define an ordered dictionary of the nodes)
        # if len(self.nodes) > 0 and len(self.schedule) == 0:
            # self.schedule = self.nodes.keys()

        # Training flag
        self.trained = False
        
    def addNodes(self, **kwargs):
        # Method to add Nodes to the Bayesian network
        # Inputs:
        #   - **kwargs: instances of a descendent of the class Variational_Node()
        # Output: dictionary with the mapping name-node(s).
        
        # Sanity checks
        assert len(kwargs) > 0, "Nothing was passed as argument"
        assert all( [isinstance(x, Node) for x in kwargs.values()] ), "The nodes have to be a Variational_Node class instances"
        assert len(set(kwargs.keys()).intersection(set(self.nodes.keys()))) == 0, "Some of the nodes is already present"
        
        # Update the nodes
        self.nodes.update(kwargs) 

        pass

    # def updateNodes(self, *kargs):
    #     # Method to update a particular set of nodes in the given order
    #     # Input:
    #     # - *kargs: the key(s) associated with the node(s) to be updated
    #     for name in kargs: 
    #         self.nodes[name].update(self)

    def setSchedule(self, schedule):
        # Method to define the schedule of updates
        # Input:
        # - schedule: list of the names of the nodes as given in the 'nodes' attribute
        assert set(schedule).issubset(self.nodes), "Adding schedule for nodes that are not defined"
        self.schedule = schedule

    def removeInactiveFactors(self, by_norm=None, by_pvar=None, by_cor=None):
        # Method to remove inactive factors

        drop_dic = {}

        # Option 1: absolute value of latent variable vectors
        #   Good: independent of likelihood type, works with pseudodata
        #   Bad: it is an approximation and covariates are never removed
        if by_norm is not None:
            Z = self.nodes["Z"].getExpectation()
            drop_dic["by_norm"] = s.where( s.absolute(Z).mean(axis=0) < by_norm )[0]

        # print s.absolute(Z)
        # print s.absolute(Z).mean(axis=0)
        # Option 2: proportion of residual variance explained by each factor
        #   Good: it is the proper way of doing it, 
        #   Bad: slow, does it work well with pseudodata?
        # if by_var is not None:
            # Z = self.nodes["Z"].getExpectation()
            # Y = self.nodes["Y"].getExpectation()
            # tau = self.nodes["tau"].getExpectation()
            # alpha = self.nodes["alpha"].getExpectation()

            # factor_pvar = s.zeros((self.dim['M'],self.dim['K']))
            # for m in xrange(self.dim['M']):
            #     residual_var = (s.var(Y[m],axis=0) - 1/tau[m]).sum()
            #     for k in xrange(self.dim["K"]):
            #         factor_var = (self.dim["D"][m]/alpha[m][k])# * s.var(Z[:,k])
            #         factor_pvar[m,k] = factor_var / residual_var
            # drop = s.where( (factor_pvar>by_pvar).sum(axis=0) == 0)[0]

        # Option 3: highly correlated factors
        # (Q) Which of the two factors should we remove? Maybe the one that explains less variation
        if by_cor is not None:
            Z = self.nodes["Z"].getExpectation()
            r = s.absolute(corr(Z.T,Z.T))
            s.fill_diagonal(r,0)
            r *= s.tri(*r.shape)
            drop_dic["by_cor"] = s.where(r>by_cor)[0]
            if len(drop_dic["by_cor"]) > 0:
                drop_dic["by_cor"] = [ s.random.choice(drop_dic["by_cor"]) ]

        # Drop the factors
        drop = s.unique(s.concatenate(drop_dic.values()))

        if len(drop) > 0:
            for node in self.nodes.keys():
                self.nodes[node].removeFactors(drop)
        self.dim['K'] -= len(drop)

        if self.dim['K']==0:
            print "Shut down all components, no structure found in the data."
            exit()

        pass


    def iterate(self):
        # Method to train the model

        # Initialise variables to monitor training
        vb_nodes = self.getVariationalNodes().keys()
        elbo = pd.DataFrame(data = s.zeros( ((int(self.options['maxiter']/self.options['elbofreq'])-1), len(vb_nodes)+1 )),
                            index = xrange(1,(int(self.options['maxiter']/self.options['elbofreq']))),
                            columns = vb_nodes+["total"] )

        # Start training
        for iter in xrange(1,self.options['maxiter']):
            t = time();

            # Update node by node, with E and M step merged
            for node in self.schedule:
                self.nodes[node].update()
                print("updated %s" % node)

            # Calculate Evidence Lower Bound
            if iter % self.options['elbofreq'] == 0:
                i = int(iter/self.options['elbofreq']) - 1
                elbo.iloc[i] = self.calculateELBO(*vb_nodes)

                if i > 0:
                    # Check convergence using the ELBO
                    delta_elbo = elbo.iloc[i]["total"]-elbo.iloc[i-1]["total"]

                    # Print ELBO monitoring
                    if self.options['verbosity'] > 0:
                        print "Trial %d, Iteration %d: time=%.2f ELBO=%.2f, deltaELBO=%.4f" % (self.trial, iter,time()-t,elbo.iloc[i]["total"], delta_elbo)
                    if self.options['verbosity'] == 2:
                        print "".join([ "%s=%.2f  " % (k,v) for k,v in elbo.iloc[i].drop("total").iteritems() ]) + "\n"

                    # Assess convergence
                    if (delta_elbo < self.options['tolerance']) and (not self.options['forceiter']):
                        print "Converged!\n"
                        break
                else:
                    print "Trial %d, Iteration 1: time=%.2f ELBO=%.2f" % (self.trial, time()-t,elbo.iloc[i]["total"])
                    if self.options['verbosity'] == 2:
                        print "".join([ "%s=%.2f  " % (k,v) for k,v in elbo.iloc[i].drop("total").iteritems() ]) + "\n"
            else:
                if self.options['verbosity'] > 0: print "Iteration %d: time=%.2f" % (iter,time()-t)

            # Save the model
            if (self.options['savefreq'] is not s.nan) and (iter % self.options['savefreq'] == 0):
                savefile = "%s/%d_model.pkl" % (self.options['savefolder'], iter)
                if self.options['verbosity'] == 2: print "Saving the model in %s\n" % savefile 
                pkl.dump(self, open(savefile,"wb"))

        # Finish by collecting the training statistics
        self.train_stats = {'elbo':elbo["total"].values, 'elbo_terms':elbo.drop("total",1) }
        self.trained = True

        pass

    def getParameters(self, *nodes):
        # Method to collect all parameters of a given set of nodes (all by default)
        # - nodes (str): name of the node
        if len(nodes) == 0: nodes = self.nodes.keys()
        params = {}
        for node in nodes:
            tmp = self.nodes[node].getParameters()
            if tmp != None: params[node] = tmp
        return params

    def getExpectations(self, only_first_moments=False, *nodes):
        # Method to collect all expectations of a given set of nodes (all by default)
        # - nodes (str): name of the node
        if len(nodes) == 0: nodes = self.nodes.keys()
        expectations = {}
        for node in nodes:
            if only_first_moments:
                tmp = self.nodes[node].getExpectation()
            else:
                tmp = self.nodes[node].getExpectations()
            expectations[node] = tmp
        return expectations

    def getNodes(self):
        # Method to return all nodes
        return self.nodes

    def getVariationalNodes(self):
        # Method to return all variational nodes
        # filter(lambda node: isinstance(self.nodes[node],Variational_Node), self.nodes.keys())
        return { k:v for k,v in self.nodes.iteritems() if isinstance(v,Variational_Node) }

    def getTrainingStats(self):
        # Method to return training statistics
        return self.train_stats

    def getTrainingOpts(self):
        # Method to return training options
        return self.options

    def getTrainingData(self):
        # Method to return training options
        return self.nodes["Y"].getValues()

    def calculateELBO(self, *nodes):
        # Method to calculate the Evidence Lower Bound for a set of nodes
        if len(nodes) == 0: nodes = self.nodes.keys()
        elbo = pd.Series(s.zeros(len(nodes)+1), index=nodes+("total",))
        for node in nodes:
            elbo[node] = float(self.nodes[node].calculateELBO())
            elbo["total"] += elbo[node]
        return elbo

        
        