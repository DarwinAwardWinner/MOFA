
"""
Module to initalise the nodes

TO-DO:
- add covariates

"""

import scipy as s
import scipy.stats as stats
from sys import path
import sklearn.decomposition
import numpy as np
path.insert(0,"../")
from nodes import *
from multiview_nodes import *
from MVRRupdates import *


# General class to initialise a Bayesian regression model
class initModel(object):
    def __init__(self, dim, data, response, lik):
        # Inputs:
        #  dim (dic): keyworded dimensionalities
        #    N for the number of samples, M for the number of views
        #    K for the number of latent variables, D for the number of features (per view, so it is a list)
        #  data (list of ndarrays of length M): observed data
        #  lik (list): likelihood type for each view
        self.data = data
        self.lik = lik
        self.N = dim["N"]
        self.M = dim["M"]
        self.D = dim["D"]
        self.response = response

        self.nodes = {}

    def getNodes(self):
        return { k:v for (k,v) in self.nodes.iteritems()}


class init_mvRR(initModel):
    def __init__(self, dim, data, response, lik):
        initModel.__init__(self, dim, data, response, lik)

    def initResponse(self):
        self.Response = Response_Node(dim=(self.N,1), value=self.response, liklihood=self.lik)
        self.nodes["Response"] = self.Response
        print("Initialsied Response node")

    def initCovariate(self, annot):
        data=np.hstack(self.data)
        #need to sve somewhere the assignment per node
        self.Covariate = Covariate_Node(dim=(self.N, s.sum(self.D)), value=data, annot=annot)
        self.nodes["Covariate"] = self.Covariate
        print("Initialised Covariate Node")


    def initCoefficients(self, qmean, qcov):
        self.Coefficient = Coefficient_Node(dim=(1,s.sum(self.D)), qmean=qmean, qcov=qcov)  
        self.nodes["Coefficient"] = self.Coefficient
        print("Initialised Coefficient Node\n")

    def initgamma(self, pa, pb, qa, qb, qE):
        gamma_list = [None]*self.M
        for m in xrange(self.M):
            gamma_list[m] = gamma_Node(dim=(1,), pa=pa[m], pb=pb[m], qa=qa[m], qb=qb[m], qE=qE[m])
        self.gamma = Multiview_Variational_Node(self.M, *gamma_list)
        self.nodes["gamma"] = self.gamma
        print("Initialised gamma Node")


    def initTau(self, pa, pb, qa, qb, qE):
        # Method to initialise the precision of the noise
        # Inputs:
        #  pa (float): 'a' parameter of the prior distribution
        #  pb (float): 'b' parameter of the prior distribution
        #  qb (float): initialisation of the 'b' parameter of the variational distribution
        #  qE (float): initial expectation of the variational distribution
        self.Tau=Tau_Node(dim=(1,), pa=pa,pb=pb,qa=qa,qb=qb,qE=qE)
        self.nodes["Tau"] = self.Tau
        print("Initalised Tau node")

    def MarkovBlanket(self):
        # Method to define the markov blanket
        #Composed of parents, children and childern's parents in the network
        self.Coefficient.addMarkovBlanket(gamma=self.gamma, Response=self.Response, Tau=self.Tau, Covariate=self.Covariate)
        self.Covariate.addMarkovBlanket(Response=self.Response)
        for m in xrange(self.M):
            self.gamma.nodes[m].addMarkovBlanket(Coefficient=self.Coefficient)
#        if self.lik[m] is "gaussian":
        self.Response.addMarkovBlanket(Coefficient=self.Coefficient, Tau=self.Tau, Covariate = self.Covariate)
        self.Tau.addMarkovBlanket(Response=self.Response, Covariate = self.Covariate, Coefficient=self.Coefficient)



# Class to iniailise the (sparse) Group Factor Analysis model
class init_scGFA(initModel):
    def __init__(self, dim, data, lik):
        initModel.__init__(self, dim, data, lik)

    def initZ(self, pmean, pvar, qmean, qvar, qE=None, qE2=None, covariates=None):
        # Method to initialise the latent variables
        # covariates (nd array): matrix of covariates with dimensions (nsamples,ncovariates)

        # Initialise first moment
        if qmean is not None:
            if isinstance(qmean,str):
                if qmean == "random":
                    qmean = stats.norm.rvs(loc=0, scale=1, size=(self.N,self.K))
                elif qmean == "orthogonal":
                    print "Not implemented"
                    exit()
                elif qmean == "pca":
                    pca = sklearn.decomposition.PCA(n_components=self.K, copy=True, whiten=True)
                    tmp = s.concatenate(self.data,axis=0).T
                    pca.fit(tmp)
                    qmean = pca.components_.T

            elif isinstance(qmean,s.ndarray):
                assert qmean.shape == (self.N,self.K)

            elif isinstance(qmean,(int,float)):
                qmean = s.ones((self.N,self.K)) * qmean

            else:
                print "Wrong initialisation for Z"
                exit()


        # Add covariates
        if covariates is not None:
            idx_covariates = s.arange(self.K)[-covariates.shape[1]:]
            qmean[:,idx_covariates] = covariates
            # qmean = s.c_[ qmean, covariates ]
            # idx_covariates = s.arange(covariates.shape[1]) + self.K

        # Initialise the node
        self.Z = Z_Node(dim=(self.N,self.K), 
                        pmean=s.ones((self.N,self.K))*pmean, 
                        pvar=s.ones((self.N,self.K))*pvar, 
                        qmean=s.ones((self.N,self.K))*qmean, 
                        qvar=s.ones((self.N,self.K))*qvar, 
                        qE=qE, qE2=qE2,
                        idx_covariates=idx_covariates)
        self.nodes["Z"] = self.Z

    def initSW(self, pmean_S0, pmean_S1, pvar_S0, pvar_S1, ptheta, qmean_S0, qmean_S1, qvar_S0, qvar_S1, qtheta, qEW_S0=None, qEW_S1=None, qES=None):

        # Method to initialise the spike-slab variable (product of bernoulli and gaussian variables)
        SW_list = [None]*self.M
        for m in xrange(self.M):
            SW_list[m] = SW_Node(
                dim=(self.D[m],self.K), 

                ptheta=s.ones((self.D[m],self.K))*ptheta[m],
                pmean_S0=s.ones((self.D[m],self.K))*pmean_S0[m],
                pvar_S0=s.ones((self.D[m],self.K))*pvar_S0[m],
                pmean_S1=s.ones((self.D[m],self.K))*pmean_S1[m],
                pvar_S1=s.ones((self.D[m],self.K))*pvar_S1[m],

                qtheta=s.ones((self.D[m],self.K))*qtheta[m],
                qmean_S0=s.ones((self.D[m],self.K))*qmean_S0[m],
                qvar_S0=s.ones((self.D[m],self.K))*qvar_S0[m],
                qmean_S1=s.ones((self.D[m],self.K))*qmean_S1[m],
                qvar_S1=s.ones((self.D[m],self.K))*qvar_S1[m],
                qES=qES[m],
                qEW_S0=qEW_S0[m],
                qEW_S1=qEW_S1[m],
                )
        self.SW = Multiview_Variational_Node(self.M, *SW_list)
        self.nodes["SW"] = self.SW

    def initAlpha(self, pa, pb, qa, qb, qE):
        # Method to initialise the precision of the group-wise ARD prior
        # Inputs:
        #  pa (float): 'a' parameter of the prior distribution
        #  pb (float): 'b' parameter of the prior distribution
        #  qb (float): initialisation of the 'b' parameter of the variational distribution
        #  qE (float): initial expectation of the variational distribution
        alpha_list = [None]*self.M
        for m in xrange(self.M):
            alpha_list[m] = Alpha_Node(dim=(self.K,), pa=pa[m], pb=pb[m], qa=qa[m], qb=qb[m], qE=qE[m])
        self.Alpha = Multiview_Variational_Node((self.K,)*self.M, *alpha_list)
        self.nodes["Alpha"] = self.Alpha

    def initTau(self, pa, pb, qa, qb, qE):
        # Method to initialise the precision of the noise
        # Inputs:
        #  pa (float): 'a' parameter of the prior distribution
        #  pb (float): 'b' parameter of the prior distribution
        #  qb (float): initialisation of the 'b' parameter of the variational distribution
        #  qE (float): initial expectation of the variational distribution
        tau_list = [None]*self.M
        for m in xrange(self.M):
            if self.lik[m] == "poisson":
                tmp = 0.25 + 0.17*s.amax(self.data[m],axis=0) 
                tau_list[m] = Constant_Node(dim=(self.D[m],), value=tmp)
            elif self.lik[m] == "bernoulli":
                tmp = s.ones(self.D[m])*0.25 
                tau_list[m] = Constant_Node(dim=(self.D[m],), value=tmp)
            elif self.lik[m] == "binomial":
                tmp = 0.25*s.amax(self.data["tot"][m],axis=0)
                tau_list[m] = Constant_Node(dim=(self.D[m],), value=tmp)
            elif self.lik[m] == "gaussian":
                tau_list[m] = Tau_Node(dim=(self.D[m],), pa=pa[m], pb=pb[m], qa=qa[m], qb=qb[m], qE=qE[m])
        self.Tau = Multiview_Mixed_Node(self.M,*tau_list)
        self.nodes["Tau"] = self.Tau


    def initY(self):
        # Method to initialise the observed data
        Y_list = [None]*self.M
        for m in xrange(self.M):
            if self.lik[m]=="gaussian":
                Y_list[m] = Y_Node(dim=(self.N,self.D[m]), value=self.data[m])
            elif self.lik[m]=="poisson":
                Y_list[m] = Poisson_PseudoY_Node(dim=(self.N,self.D[m]), obs=self.data[m], E=None)
            elif self.lik[m]=="bernoulli":
                Y_list[m] = Bernoulli_PseudoY_Node(dim=(self.N,self.D[m]), obs=self.data[m], E=None)
            elif self.lik[m]=="binomial":
                Y_list[m] = Binomial_PseudoY_Node(dim=(self.N,self.D[m]), tot=data["tot"][m], obs=data["obs"][m], E=None)
        self.Y = Multiview_Mixed_Node(self.M, *Y_list)
        self.nodes["Y"] = self.Y

    def initThetaLearn(self, pa, pb, qa, qb, qE):
        # Method to initialise the theta node
        # TO-DO: ADD ANNOTATIONS
        Theta_list = [None] * self.M
        for m in xrange(self.M):
            Theta_list[m] = Theta_Node(dim=(self.K,), pa=pa[m], pb=pb[m], qa=qa[m], qb=qb[m], qE=qE[m])
        self.Theta = Multiview_Variational_Node(self.M, *Theta_list)
        self.nodes["Theta"] = self.Theta

    def initThetaConst(self, value):
        # Method to initialise the theta node
        Theta_list = [None] * self.M
        for m in xrange(self.M):
            Theta_list[m] = Theta_Constant_Node(dim=(self.K,), value=value[m])
        Theta = Multiview_Mixed_Node(self.M, *Theta_list)
        self.nodes["Theta"] = self.Theta

    def initExpectations(self, *nodes):
        # Method to initialise the expectations of some nodes
        for node in nodes:
            self.nodes[node].updateExpectations()

    def MarkovBlanket(self):
        # Method to define the markov blanket
        self.Z.addMarkovBlanket(SW=self.SW, Tau=self.Tau, Y=self.Y)
        for m in xrange(self.M):
            self.Theta.nodes[m].addMarkovBlanket(SW=self.SW.nodes[m])
            self.Alpha.nodes[m].addMarkovBlanket(SW=self.SW.nodes[m])
            self.SW.nodes[m].addMarkovBlanket(Z=self.Z, Tau=self.Tau.nodes[m], Alpha=self.Alpha.nodes[m], Y=self.Y.nodes[m], Theta=self.Theta.nodes[m])
            if self.lik[m] is "gaussian":
                self.Y.nodes[m].addMarkovBlanket(Z=self.Z, SW=self.SW.nodes[m], Tau=self.Tau.nodes[m])
                self.Tau.nodes[m].addMarkovBlanket(SW=self.SW.nodes[m], Z=self.Z, Y=self.Y.nodes[m])
            else:
                self.Y.nodes[m].addMarkovBlanket(Z=self.Z, W=self.SW.nodes[m], kappa=self.Tau.nodes[m])

