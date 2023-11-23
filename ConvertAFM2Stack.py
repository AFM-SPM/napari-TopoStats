import napari
from skimage.io import imread
import numpy
import copy

def AFM2Stack(
		image: "Napari.types.ImageData",
		numslices: int
		):
	shape = image.shape

	output = numpy.empty((numslices, shape[0], shape[1]))
	minval = image.min()
	maxval = image.max()
	totalrange = maxval - minval
	increment = totalrange / numslices

	currentZ = minval
	for z in range(0, numslices):
		dup = copy.deepcopy(image)
		dup[dup > z] = currentZ
		output[z,:,:] = dup
		currentZ += increment

	return output




