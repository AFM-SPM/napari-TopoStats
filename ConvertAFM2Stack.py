import napari
from skimage.io import imread
import numpy
import copy

viewer = napari.Viewer()

original = imread("H:\\NapariWorkshop\\firezproject.tif") # To replace with input
viewer.add_image(original) # Remove in final

numslices = 256 # To replace with input

shape = original.shape
# print(shape)
stacked = numpy.empty((numslices, shape[0], shape[1]))
# print(stacked.shape)

# Iterates through each slice in 
for z in range(0, numslices):
	dup = copy.deepcopy(original)
	dup[dup > z] = z
	stacked[z,:,:] = dup

# Displays the stacked image
viewer.add_image(stacked, name='Output from load AFM', colormap='inferno')




