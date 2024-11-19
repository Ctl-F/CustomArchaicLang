from lark import Lark, Transformer, v_args

grammar = ""

header_filename = ""
source_filename = ""
header_body = []
source_body = []
source_includes = []
source_functions = []
global_functions = []

def append_all(list, *args):
    for arg in args:
        list.append(arg)
    return list

def compile_inline_c(c_node):
    pass

def compile_function(function_node):
    isGlobal = False
    first = 0
    if function_node.children[0].data == "global":
        first = 1
        isGlobal = True
    name = function_node.children[first]
    params = []
    

def compile_cinclude(include_node):
    global source_includes
    source_includes.append("#include <%s>\n" % include_node[1:-1])
    pass

def compile_lib(tree):
    global header_filename, header_body, source_filename, source_body
    global source_includes, source_functions, global_functions
    
    lib_name = "calib" + tree.children[0]
    
    header_filename = lib_name + ".h"
    source_filename = lib_name + ".c"

    header_body = append_all(header_body, "#ifndef __", lib_name, "__\n")
    header_body = append_all(header_body, "#define __", lib_name, "__\n\n")
    source_includes = append_all(source_includes, "#include \"", lib_name, ".h\"\n\n")

    functions = []

    unit_body = tree.children[1]

    for item in unit_body.children:
        match item.data:
            case "c_include":
                compile_cinclude(item.children[0])
            case "function":
                compile_function(item)
            case _:
                print("Unexpected item %s" % item)
                return
    


    header_body = append_all(header_body, "\n#endif //__", lib_name, "__\n")
    with open(header_filename, "w") as f:
        f.write("".join(header_body))

    with open(source_filename, "w") as f:
        f.write("".join(source_includes))
        f.write("".join(source_body))

    header_filename = ""
    source_filename = ""
    header_body = []
    source_body = []
    source_includes = []
    source_functions = []
    global_functions = []
    pass

def compile(tree):
    if(tree.data == "multi_prgm"):
        for child in tree.children:
            compile(child)
        return
    if tree.data == "begin_lib":
        compile_lib(tree)
    elif tree.data == "begin_proc":
        print("proc")
        pass
    elif tree.data == "begin_test":
        print("test")
        pass
    else:
        print("Unexpected")


def main():
    with open("grammar.ebnf", "r") as f:
        grammar = f.read()


    code = ""
    with open("example.cal", "r") as f:
        code = f.read()

    parser = Lark(grammar, parser="lalr")
    tree = parser.parse(code)
    #print(tree.pretty())

    compile(tree)

if __name__ == "__main__":
    main()
