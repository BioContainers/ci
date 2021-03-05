from dockerfile_parse import DockerfileParser
from dockerfile_parse.util import WordSplitter
import sys

def reload_arg_to_env (dfp, content):
	recipe_args = dict()
	for crtInstr in dfp.structure:
		if crtInstr['instruction']=="ARG":
			parts = crtInstr['value'].split('=')
			if len(parts) != 2:
				print("An ARG instruction is wrongly formatted")
				sys.exit(1)
			#If an ARG can be parsed, it is added to a temp env dictionary
			crt_value = WordSplitter(parts[1]).dequote()
			recipe_args[parts[0]]=crt_value

	if len(recipe_args.keys())>0:
		#We must re-initialize the parser while including the ARG dictionary
		print ("Updating parser with newly found ARG instructions")
		dfp = DockerfileParser(parent_env = recipe_args)
		dfp.content = content

	return dfp
