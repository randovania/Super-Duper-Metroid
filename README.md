# Super-Duper-Metroid
Super Duper Metroid is a Super Metroid patcher and interface program, intended for use with randomizer programs. SDM is a **work in progress**, and is likely very broken in its current state. SDM requires an installation of Python 3 to work, although I haven't done any testing to determine which versions precisely work, and requires a Headerless ROM file to modify. Remember that video game piracy is a crime - only use legally obtained copies of the game Super Metroid with this program. Has been tested for NTSC.

# Building
Requires an adequate version of python  
Steps:  
1.) Clone this repository  
2.) Open a terminal in the repository's root  
3.) Create a virtual environment by running `py -3.7 -m venv venv`  
4.) Open virtual environment with `venv\scripts\activate`  
5.) Install requirements by running `python -m pip install -r requirements.txt`  
6.) Build Cython code by running `python setup.py`  
  
You can now run scripts from the project from terminal, using the virtual environment.  

# Credit
Credit goes to Samuel Roy for writing most of this code.  
Kazuto wrote the More Efficient Item PLMs Hack, which is recreated in parts of this code.  
Metroid Construction and Kejardon provided a lot of documentation which I made use of.  
PHOSPHOTiDYL wrote the Skip Intro Saves hack, which is included in this program.  
Total, Fusda, and Leodox were responsible for the IPS patches.  
