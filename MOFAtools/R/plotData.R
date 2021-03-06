
##############################################
## Functions to visualise the training data ##
##############################################

#' @title plotDataHeatmap: plot heatmap of selected features
#' @name plotDataHeatmap
#' @description Function to plot a heatmap for selected features, usually the ones with highest loadings in a given latent factor.
#' @param object a \code{\link{MOFAmodel}} object.
#' @param view character vector with the view name, or numeric vector with the index of the view.
#' @param factor character vector with the factor name, or numeric vector with the index of the factor.
#' @param features if an integer, the total number of features to plot, based on the absolute value of the loading (50 by default).
#' If a character vector, a set of manually-defined features to plot.
#' @param includeWeights boolean indicating whether to include the weight of each feature as an extra annotation in the heatmap (FALSE by default).
#' @param transpose boolean indicating whether to transpose the output heatmap (FALSE by default, which corresponds to features as rows and samples as columns)
#' @param imputed boolean indicating whether to use the imputed data (FALSE by default)
#' @param ... further arguments that can be passed to \code{\link[pheatmap]{pheatmap}}
#' @details One of the first steps for the annotation of factors is to visualise the corresponding loadings using \code{\link{plotWeights}} or \code{\link{plotTopWeights}}. \cr
#' These methods show you which features drive the heterogeneity of each factor. However, one might also be interested in directly visualising the heterogeneity in the original data, rather than looking at "abstract" weights. \cr
#' This method plots a heatmap for selected features (by default the top ones with highest loading), which should reveal the underlying pattern of the data that is captured by the latent factor. \cr
#' A similar function for doing scatterplots rather than heatmaps is \code{\link{plotDataScatter}}.
#' @import pheatmap
#' @export
plotDataHeatmap <- function(object, view, factor, features = 50, includeWeights = FALSE, transpose = FALSE, imputed = FALSE, ...) {
  
  # Sanity checks
  if (class(object) != "MOFAmodel") stop("'object' has to be an instance of MOFAmodel")
  stopifnot(view %in% viewNames(object))
  stopifnot(factor %in% factorNames(object)) 
  
  # Collect relevant data
  W <- getExpectations(object,"SW")[[view]][,factor]
  Z <- getFactors(object)[,factor]
  Z <- Z[!is.na(Z)]
  
  if (imputed) {
    data <- getImputedData(object, view)[[1]][,names(Z)]
  } else {
    data <- getTrainData(object, view)[[1]][,names(Z)]
  }
  
  # Ignore samples with full missing views
  data <- data[,apply(data, 2, function(x) !all(is.na(x)))]
  
  # Define features
  if (class(features) == "numeric") {
    features <- names(tail(sort(abs(W)), n=features))
    stopifnot(all(features %in% featureNames(object)[[view]]))
  } else if (class(features)=="character") {
    stopifnot(all(features %in% featureNames(object)[[view]]))
  } else {
    stop("Features need to be either a numeric or character vector")
  }
  
  # Sort samples according to latent factors
  order_samples <- names(sort(Z, decreasing=T))
  order_samples <- order_samples[order_samples %in% colnames(data)]
  data <- data[features,order_samples]
  
  # Transpose the data
  if (transpose==T) { data <- t(data) }
  
  # Plot heatmap
  # if(is.null(main)) main <- paste(view, "observations for the top weighted features of factor", factor)
  if (includeWeights) { 
    anno <- data.frame(row.names=names(W[features]), weight=W[features]) 
    if (transpose==T) {
      pheatmap::pheatmap(t(data), annotation_col=anno, ...)
    } else {
      pheatmap::pheatmap(t(data), annotation_row=anno, ...)
    }
  } else {
    pheatmap::pheatmap(t(data), ...)
  }
  
}



#' @title plotDataScatter: scatterplot of features against latent factors
#' @name plotDataScatter
#' @description Function to do a scatterplot of feature(s) against a latent factor.
#' @param object a \code{\link{MOFAmodel}} object.
#' @param view character vector with a view name, or numeric vector with the index of the view.
#' @param factor character vector with a factor name, or numeric vector with the index of the factor.
#' @param features if an integer, the total number of features to plot (10 by default). If a character vector, a set of manually-defined features.
#' @param color_by specifies groups or values used to color points. This can be either a character giving the name of a feature, or the name of covariate from the MultiAssayExperiment object, or a factor vector of same length as the number of samples.
#' @param shape_by specifies groups or values used to shape points, same behaviour as 'color_by'
#' @details One of the first steps for the annotation of factors is to visualise the loadings using \code{\link{plotWeights}} or \code{\link{plotTopWeights}}. \cr
#' These methods show you which features drive the heterogeneity of each factor. However, one might also be interested in visualising the heterogeneity in the original data, rather than looking at "abstract" weights. \cr
#' This method generates scatterplots of features against factors, so that you can observe the association between them. \cr
#' A similar function for doing heatmaps rather than scatterplots is \code{\link{plotDataHeatmap}}.
#' @import ggplot2
#' @import dplyr
#' @export

plotDataScatter <- function(object, view, factor, features = 10, color_by = NULL, shape_by = NULL) {
  
  # Sanity checks
  if (class(object) != "MOFAmodel") stop("'object' has to be an instance of MOFAmodel")
  stopifnot(length(factor)==1)
  stopifnot(length(view)==1)
  if (!factor %in% factorNames(object)) stop(sprintf("The factor %s is not present in the object",factor))
  if (!view %in% viewNames(object)) stop(sprintf("The view %s is not present in the object",view))
  
  # Collect relevant data
  N <- getDimensions(object)[["N"]]
  Z <- getFactors(object)[,factor]
  W <- getWeights(views=view, factors=factor)
  Y <- object@TrainData[[view]]
  
  # Get features
  if (class(features) == "numeric") {
    tmp <- names(tail(sort(abs(W)), n=features))
    stopifnot(all(tmp %in% featureNames(object)[[view]]))
  } else if (class(features)=="character") {
    stopifnot(all(features %in% featureNames(object)[[view]]))
  } else {
    stop("Features need to be either a numeric or character vector")
  }
  W <- W[features]
  Y <- Y[features,]
  
  
  # Set color
  if (!is.null(color_by)) {
    colorLegend <- T
    
    # 'color_by' is the name of a covariate 
    if (length(color_by) == 1 & is.character(color_by)) { 
      color_by <- as.factor(getCovariates(object, color_by))
    
    # 'color_by' is a vector of length N
    } else if (length(color_by) > 1) { 
      stopifnot(length(color_by) == N)
      
    # 'color_by' not recognised
    } else {
      stop("'color_by' was specified but it was not recognised, please read the documentation")
    }
    
  } else {
    color_by <- rep(TRUE,N)
    colorLegend <- F
  }
  
  # Set shape
  if (!is.null(shape_by)) {
    shapeLegend <- T
    
    # 'shape_by' is the name of a covariate 
    if (length(shape_by) == 1 & is.character(shape_by)) { 
      shape_by <- as.factor(getCovariates(object, shape_by))
      
    # 'shape_by is a vector of length N
    } else if (length(shape_by) > 1) { 
      stopifnot(length(shape_by) == N)
      shape_by <- as.factor(shape_by)
      
    # 'shape_by not recognised
    } else {
      stop("'shape_by' was specified but it was not recognised, please read the documentation")
    }
    
  } else {
    shape_by <- rep(TRUE,N)
    shapeLegend <- F
  }
  
  
  # Create data frame 
  df1 <- data.frame(sample=names(Z), x = Z, shape_by = shape_by, color_by = color_by, stringsAsFactors=F)
  df2 <- getTrainData(object, views=view, features = list(features), as.data.frame=T)
  df <- left_join(df1,df2, by="sample")
  
  #remove values missing color or shape annotation
  # if(!showMissing) df <- df[!(is.nan(df$shape_by) & !(is.nan(df$color_by))]
  
  # Generate plot
  p <- ggplot(df, aes(x, value, color = color_by, shape = shape_by)) + 
    geom_point(color="black") + 
    stat_smooth(method="lm", color="blue", alpha=0.5) +
    facet_wrap(~feature, scales="free_y") +
    scale_shape_manual(values=c(19,1,2:18)[1:length(unique(shape_by))]) +
    theme(plot.margin = margin(20, 20, 10, 10), 
          axis.text = element_text(size = rel(1), color = "black"), 
          axis.title = element_text(size = 16), 
          axis.title.y = element_text(size = rel(1.1), margin = margin(0, 15, 0, 0)), 
          axis.title.x = element_text(size = rel(1.1), margin = margin(15, 0, 0, 0)), 
          axis.line = element_line(color = "black", size = 0.5), 
          axis.ticks = element_line(color = "black", size = 0.5),
          panel.border = element_blank(), 
          panel.grid.major = element_blank(),
          panel.grid.minor = element_blank(), 
          panel.background = element_blank(),
          legend.key = element_rect(fill = "white")
          # legend.text = element_text(size = titlesize),
          # legend.title = element_text(size =titlesize)
          )
  if (colorLegend) { p <- p + labs(color = name_color) } else { p <- p + guides(color = FALSE) }
  if (shapeLegend) { p <- p + labs(shape = name_shape) }  else { p <- p + guides(shape = FALSE) }
  
  return(p)
}


