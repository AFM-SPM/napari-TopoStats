/*
 *Convert AFM image to stack of binary images
 */
 
run("Close All");
print("\\Clear");
print("  ");
print("Code 1 starting...");
print("  ");

//define directory location of your file
print("  ");
print("Select the folder where the image you want to Cut down into slices is located");
print("  ");
print(" ______________ ");
dir1 = getDirectory("Choose Source Directory");


//write the exact name of your FILE WITH EXTENSION 
print("  ");
print("Now write the exact name of the image plus the extension using the format name.extension");
print("  ");
print(" ______________ ");
name1= getString("File name.extension", "Image1.tif");

//define in how many slides you want to cut the image
number_slides=getNumber("Tell the number of slices you want to make (the maximum is 255)", 255);

//This is to avoid seeing all the actions the system does
setBatchMode(true);

/*Use the loop to repeat the same process X times, The maximum number is 255 which is the number of times we can divide 
this image in binary using the threshold.
*/
print("  ");
print("Code 1 is making the slices now...");
print("  ");

for(i=0;i<number_slides;i++){
	
	//Open image already transformed into grey-scale
	open(dir1+name1);

	//Convert image to 8 bit so it can be thresholded.
	run("8-bit");

	//threshold image (image in binary slices where the areas where there is no material are considered pores).
	setAutoThreshold("Otsu");

	//define variables

	a = 0;
	b = number_slides-i;

	setThreshold(a, b);

	//apply the threshold, select false to put holes in black and true to put them in white

	setOption("BlackBackground", true);
	run("Convert to Mask");

	//clean up the binary image 
	//run("Fill Holes");
	//run("Open");

	//separate holes by erode
	//run("Dilate");
	//run("Watershed");
	//run("Erode");
}
print(" ______________ ");
print("  ");
print("Code 1 has finished making the slices and it joining them into a STACK now");

//convert to stack
run("Images to Stack", "name=Stack2 title=[] use");

//write the name of the stack and the stack sequence WITHOUT EXTENSION 
print("  ");
print(" ______________ ");
print("Write the name of the STACK finishing it with an underscore (_) this is going to be followed by numbers for each slice");
print("  ");
print(" ______________ ");
name2 = getString("File name", "2nN_stack_");

//Allocate the directory to save the STACK and GIF into the same place as where the image is.
dir2 = dir1;

//Save stack as .tiff and .gif
saveAs("tiff", dir2+name2);
saveAs("gif", dir2+name2);

//Save the stack as Image Sequence for the analysis with code 2 (it might be that lines 66 and 67 don't work in Windowd, let me know if the stacks are not being properly saved)
print("  ");
print("Finally, the STACK is going to be saved as an image sequence, select an EMPTY folder named Stack");
print("  ");
print(" ______________ ")
dir3 = getDirectory("Choose a Directory");
run("Image Sequence... ", "format=TIFF name="+name2+" digits=3 save=["+dir3+"]");

//Clear Log and print "Finish"
print("\\Clear");
print("Code_1_Finished");