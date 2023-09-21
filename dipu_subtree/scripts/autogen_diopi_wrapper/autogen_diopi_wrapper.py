# Copyright (c) 2023, DeepLink.
import yaml
import re
import json
import os
from collections import OrderedDict
from typing import Mapping, Match, Optional, Sequence
from diopi_wrapper_template import diopi_wrapper_file_template_content,\
    diopi_wrapper_function_template_content, op_register_template_content,\
    custom_autograd_template_content, autocompare_template_content,\
    op_with_custom_fallback_register_template_content

class CodeTemplate:
    substitution_str = r"(^[^\n\S]*)?\$([^\d\W]\w*|\{,?[^\d\W]\w*\,?})"
    substitution = re.compile(substitution_str, re.MULTILINE)

    pattern: str
    filename: str

    @staticmethod
    def from_file(filename: str) -> "CodeTemplate":
        with open(filename, "r") as f:
            return CodeTemplate(f.read(), filename)

    def __init__(self, pattern: str, filename: str = "") -> None:
        self.pattern = pattern
        self.filename = filename

    def substitute(
        self, env: Optional[Mapping[str, object]] = None, **kwargs: object
    ) -> str:
        if env is None:
            env = {}

        def lookup(v: str) -> object:
            assert env is not None
            return kwargs[v] if v in kwargs else env[v]

        def indent_lines(indent: str, v: Sequence[object]) -> str:
            return "".join(
                [indent + l + "\n" for e in v for l in str(e).splitlines()]
            ).rstrip()

        def replace(match: Match[str]) -> str:
            indent = match.group(1)
            key = match.group(2)
            comma_before = ""
            comma_after = ""
            if key[0] == "{":
                key = key[1:-1]
                if key[0] == ",":
                    comma_before = ", "
                    key = key[1:]
                if key[-1] == ",":
                    comma_after = ", "
                    key = key[:-1]
            v = lookup(key)
            if indent is not None:
                if not isinstance(v, list):
                    v = [v]
                return indent_lines(indent, v)
            elif isinstance(v, list):
                middle = ", ".join([str(x) for x in v])
                if len(v) == 0:
                    return middle
                return comma_before + middle + comma_after
            else:
                return str(v)

        return self.substitution.sub(replace, self.pattern)


def get_fun_name_from_cppsignature(cppnature):
    return re.search(r'[a-zA-Z_:]+[\w\d:]+\(' , cppnature).group().replace('(', '')


def get_op_name_from_schema(schema):
    op_name = schema[0:schema.find('(')]
    op_name = re.sub('aten::', '', op_name)
    return op_name

def create_fun_name_from_schema(schema):
    schema = schema.strip()
    op_name = schema[0:schema.find('(')]
    op_name = op_name.replace('.','_')
    op_name = "dipu_" + re.sub('aten::', '', op_name)
    op_name = op_name.lower()
    return op_name

def create_return_code_frome_schema(schema, allow_return_ref = True):
    schema = re.sub('Tensor\([a-z]\)' , 'Tensor', schema)
    return_code = schema[schema.find('->'):].replace('->', '').strip()
    return_code = re.sub('\([a-zA-Z]!\)', '&' , return_code)
    return_code = re.sub('Tensor', 'at::Tensor' , return_code)
    return_code = re.sub('([\w_\d:&]+)[ ]+([\w\d_]+)?', R'\1', return_code)
    return_code = re.sub('\(', 'std::tuple<', return_code)
    return_code = re.sub('\)', '> ' ,return_code)
    if allow_return_ref == False:
        return_code = return_code.replace('&', '')
    return return_code

def create_transform_input_to_cpu_code(fun_config):
    input_process_code = ''
    schema = fun_config['schema']
    inputs = re.findall('Tensor +([\w\d_]+)', schema[:schema.find('->')])
    for input in inputs:
        input_process_code += f"at::Tensor {input}_cpu = {input}.cpu();\n"

    optional_inputs = re.findall('Tensor *\? +([\w\d_]+)', schema[:schema.find('->')])
    for input in optional_inputs:
        input_process_code += f"\nc10::optional<at::Tensor> {input}_cpu = {input}.has_value() && {input}.value().defined() ? c10::make_optional<at::Tensor>({input}.value().cpu()) : {input};\n"

    optional_tensor_list_inputs = re.findall('Tensor *\? *\[ *\] +([\w\d_]+)', schema[:schema.find('->')])
    for input in optional_tensor_list_inputs:
        input_process_code += f"\nc10::List<c10::optional<at::Tensor>> {input}_cpu;\n"
        input_process_code += f"for (int i = 0; i < {input}.size();++i)" + " {\n"
        input_process_code += f"\t{input}_cpu.push_back({input}[i].has_value() && {input}[i].value().defined() ? c10::make_optional<at::Tensor>({input}[i].value().cpu()) : {input}[i]);\n"
        input_process_code += "}\n"

    outputs = re.findall('Tensor\([a-z]!\)[ ]+([\w\d_]+){1}', schema[:schema.find('->')])
    for output in outputs:
        if output.strip().endswith('?'):
            output = output.replace('?', '')
            input_process_code += f"\nc10::optional<at::Tensor> {output}_cpu = {output}.has_value() && {output}.value().defined() ? c10::make_optional<at::Tensor>({output}.value().cpu() : {output};\n"
        else:
            input_process_code += f"at::Tensor {output}_cpu = {output}.cpu();\n"


    tensors_arrays = re.findall('Tensor *\[ *\] * +([\w\d_]+)', schema[:schema.find('->')])
    tensors_arrays += re.findall('ITensorListRef *&? +([\w\d_]+)', schema[:schema.find('->')])
    if len(tensors_arrays) > 0:
        for tensors_arg in tensors_arrays:
            input_process_code += f"std::vector<at::Tensor> {tensors_arg}_cpu({tensors_arg}.size());\n";
            input_process_code += f"std::transform({tensors_arg}.begin(), {tensors_arg}.end(), {tensors_arg}_cpu.begin(), [](const at::Tensor& tensor)" + '{return tensor.cpu();});\n'

    return input_process_code


def create_print_op_args_code(fun_config):
    args_name_list = create_args_name_list_from_schema(fun_config['schema'])
    opname = get_op_name_from_schema(fun_config['schema'])
    inputs = args_name_list.split(',') + get_function_need_alloc_args_from_schema(fun_config['schema'])
    code = ''
    if len(inputs) < 0:
        return code
    code += "if (dumpOpArgLevel() > 1) {\n"
    for input in inputs:
        input = input.strip()
        code += f'\tstd::cout << "\t{opname}:\t{input}:" << dumpArg({input}) << std::endl;\n'
    code += "}"
    return code


def create_param_list_from_schema(schema):
    param_list = schema[schema.find('(') + 1 : schema.find('->')].strip()
    param_list = param_list[0:param_list.rfind(')')]
    args_type_map = OrderedDict({
        'Tensor\([a-z]\)' : 'Tensor',
        '[ ]*\([a-zA-Z]!\)' : '&',
        'str\?' : 'c10::optional<c10::string_view>',
        '([, \(]{1})str ' : R'\1c10::string_view ',
        'ScalarType[ ]*\?' : 'c10::optional<at::ScalarType>',
        'ScalarType[ ]+([\w\d_]+)' : R'at::ScalarType \1',
        'Scalar[ ]*\? *([\w\d_]+)' :  R'const c10::optional<at::Scalar>& \1',
        'Generator ?\?' : 'c10::optional<at::Generator>',
        'Device ?\?' : 'c10::optional<c10::Device>',
        'Layout ?\?' : 'c10::optional<at::Layout>' ,
        'Tensor ?\? *\[ *\]' : R'const c10::List<c10::optional<at::Tensor>>&' ,
        'Tensor ?\?' : 'const c10::optional<at::Tensor>&' ,
        'int ?\?' : 'c10::optional<int64_t>' ,
        'float ?\?' : 'c10::optional<double>' ,
        '([\(, ]*)int ([\w\d_]+)' : R'\1int64_t \2',
        '([\(, ]*)float ([\w\d_]+)' : R'\1double \2',
        '([\(, ]*)SymInt ([\w\d_]+)' : R'\1c10::SymInt \2',
        '([\(, ]*)SymInt *\[[ \d]*\] ([\w\d_]+)' : R'\1c10::SymIntArrayRef \2',
        '([\(, ]*)SymInt *\[[ \d]*\] *\? +([\w\d_]+)' : R'\1at::OptionalSymIntArrayRef \2',
        'int\[\d*\] +([\w\d_]+)' : R'at::IntArrayRef \1' ,
        '([a-zA-Z0-9]+)\?' : R'c10::optional<\1>',
        'Tensor *\[ *\]' : 'at::ArrayRef<at::Tensor>' ,
        'Tensor[ ]*& +([\w\d_]+)' : R'at::Tensor& \1' ,
        'Tensor[ ]+([\w\d_]+)' : R'const at::Tensor& \1' ,
        'Scalar ' : R'const at::Scalar& ' ,
        '([, \(]+)int\[\d\]\?' : R'\1at::OptionalIntArrayRef',
        'int *\[ *\d+\ *]' : 'at::IntArrayRef' ,
        'bool\[(\d+)\]' : R'::std::array<bool,\1>' ,
        '\*[ ,]+' : '',
        '\=[ ]*\[ *\]' : '',
        '=[ ]*\'?\w*-?\.?[\d ]*\'?' : '',
    })
    for pattern, cpp_type in args_type_map.items():
        param_list = re.sub(str(pattern), str(cpp_type), param_list)
    return param_list


def get_function_inputs_from_schema(schema):
    param_list = create_param_list_from_schema(schema)
    ins = []
    for args in param_list.split(','):
        args = args.strip()
        tensor_match_result = re.search('Tensor[ ]*&+', args)
        if tensor_match_result is not None:
            in_match_result = re.search('const[ ]+[at::]*Tensor[ &]*', args)
            if in_match_result is not None:
                ins.append(args[in_match_result.span()[1]::].strip())
        opt_tensor_match_result = re.search('const[ ]+c10::optional<at::Tensor>[ &]*([a-zA-Z_0-9]+)', args)
        if opt_tensor_match_result is not None:
            opt_tensor = re.sub('const[ ]+c10::optional<at::Tensor>[ &]*([a-zA-Z_]+)', r'\1', args).strip()
            ins.append(opt_tensor + '?')
    return ins


def get_function_need_alloc_args_from_schema(schema):
    outputs = []
    param_list = schema[schema.find('->') + 2 : ].strip()
    outputs += re.findall('\(?Tensor[ ]*([\w\d_]+){1}',  param_list)

    no_name_args = re.findall('Tensor[ ]*(?!\([a-z]!\))(?![\w\d_ ]+)',  param_list)
    no_name_args_num = len(no_name_args)
    for i in range(no_name_args_num):
        outputs.append('out' + (str(i) if no_name_args_num > 1 else ''))

    return outputs


def get_function_outputs_from_schema(schema):
    outputs = re.findall('Tensor\([a-z]!\)[ ]+([\w\d_]+){1}', schema)
    outputs += get_function_need_alloc_args_from_schema(schema)
    outputs = list(set(outputs))
    return outputs

def get_function_scalar_args_from_schema(schema):
    param_list = schema[schema.find('(') + 1 : schema.find('->')].strip()
    param_list = param_list[0:param_list.rfind(')')]
    scalars = []
    for args in param_list.split(','):
        args = args.strip()
        scalar_match_result = re.search('[ ]?Scalar[ ]+', args)
        opt_scalar_match_result = re.search('Scalar[ ][\?]+', args)
        if scalar_match_result is not None and opt_scalar_match_result is None:
            scalar_param = args[scalar_match_result.span()[1]:].strip()
            scalar_param = re.sub('=.*,{1}', ',', scalar_param)
            scalar_param = re.sub('=.*', '', scalar_param)
            scalars.append(scalar_param.strip())
    return scalars

def get_function_optional_scalar_args_from_schema(schema):
    param_list = schema[schema.find('(') + 1 : schema.find('->')].strip()
    param_list = param_list[0:param_list.rfind(')')]
    return re.findall('Scalar *\? +([\w\d_]+)', param_list)


def get_function_int_array_args_from_schema(schema):
    param_list = create_param_list_from_schema(schema)
    int_arrays = []
    for args in param_list.split(','):
        args = args.strip()
        match_result = re.search('[^Optional]SymIntArray[\w\d]*', args)
        if match_result is not None:
            int_array_param = args[match_result.span()[1]:].strip()
            int_array_param = re.sub('=.*,{1}', ',', int_array_param)
            int_array_param = re.sub('=.*', '', int_array_param)
            int_arrays.append(int_array_param.strip())
    return int_arrays


def get_function_return_param_from_schema(schema):
    return_schema= schema[schema.find('->' ) + 2:].strip()
    params = []
    return_params = return_schema.split(',')
    for i in range(len(return_params)):
        args = return_params[i]
        inplace_match = re.search('Tensor\([a-zA-Z]+!\)', args)
        pure_out_match = re.search('Tensor[ ,]?', args)
        if inplace_match is not None:
            arg_label = re.sub('.*(\(.*\))', r'\1',inplace_match.group())
            index = schema.find(arg_label) + len(arg_label)
            param = re.search("[a-zA-Z0-9_::]+", schema[index:]).group()
            params.append(param)
        elif inplace_match is None and pure_out_match is not None:
            name_from_schema = re.sub('\(?Tensor[ ]+([\w\d_]+)\)?', R'\1', args)
            if name_from_schema == args:
                name = "out" + (str(i) if len(return_params) > 1 else '')
            else:
                name = name_from_schema
            params.append(name)
    return params


def create_call_diop_interface_code_from_schema(schema):
    schema = schema.replace('aten::', '').strip()
    schema = schema.replace('_.', 'Inp')
    schema = schema.replace('.', '')

    outs = re.findall(",? *Tensor *\(\w+!\) *\w+", schema)[::-1]
    schema = re.sub(",? *Tensor *\(\w+!\) *\w+", '', schema)
    index = schema.find('(') + 1
    for args in outs:
        schema = schema[0:index] + args.replace(',', '') + ', ' + schema[index:]

    schema = schema.replace('(', '(ctx, ', 1)
    return_index = schema.find('->')

    if return_index > 0:
        return_args = schema[return_index + 2 :].strip()
        if re.search('Tensor[ ]*\([\w]+!\)', return_args) is None:
            return_args = re.sub('Tensor[ ]*\([\w]+!\)[ ]*', '', return_args)
            return_args = re.sub('[\(\)]', '', return_args).strip()
            outs = return_args.split(',')
            retucn_code = ''
            for i in range(len(outs)):
                retucn_code += 'out'
                if len(outs) > 1:
                    retucn_code += str(i)
                if i < len(outs) - 1:
                    retucn_code += ', '
            schema = re.sub('\([ ]*ctx', '(ctx, ' + retucn_code, schema)
    schema = schema[0 : schema.find('->')]

    for key in ['Tensor[ ]*\([\w!]+\)', 'Tensor[ ]*\?', 'Tensor[ ]*', 'bool', 'float', 'str[ ]*\?', '[,]? *\* *', '=[\w]+']:
        index = schema.find('(')
        schema = schema[0:index] +  re.sub(key , '', schema[index:])

    index = schema.find('(')
    schema = schema[0:index] +  re.sub('Scalar[ ]*' , '&', schema[index:])

    for key in ['out', '_mode', 'Tensor', '_', '[nN]{1}ative_']:
        index = schema.find('(')
        schema = re.sub(key , '', schema[:index]) + schema[index:]

    schema = 'diopi' + schema[0].upper() + schema[1:]
    schema = re.sub(' *, *', ', ', schema)
    schema = re.sub(' *, *,', ', ', schema)

    return schema


def create_cpp_signature_from_schema(schema):
    return_code = create_return_code_frome_schema(schema)
    fun_name = create_fun_name_from_schema(schema)
    param_list = create_param_list_from_schema(schema)
    cppsignature_template = CodeTemplate("$return_code $fun_name($param_list)")
    cppsignature = cppsignature_template.substitute(
        return_code=[return_code],
        fun_name=[fun_name],
        param_list=[param_list]
    )
    return cppsignature


def create_args_name_list_from_schema(schema):
    code = '';
    param_list = create_param_list_from_schema(schema)
    args_list = re.findall('([\w\d_<>:& ]+ )([\w\d_]+)', param_list)
    for i in range(len(args_list)):
        arg_type, arg_name = args_list[i]
        code += arg_name
        if i < len(args_list) - 1:
            code += ', '
    return code

def create_call_cpp_function_code_from_schema(schema):
    code = create_fun_name_from_schema(schema) + '(' + create_args_name_list_from_schema(schema) + ');'
    return code


def create_call_aten_cpu_cpp_function_code_from_schema(schema):
    opname = get_op_name_from_schema(schema)
    #opname = re.sub('\.[\w]+_out', '_outf', opname)
    opname = re.sub('\.(Scalar)?(Tensor)?[\w_\d]*_out', '_outf', opname)
    opname = re.sub('\.out[\w_\d]*', '_outf', opname)
    opname = re.sub('\.Tensor_Scalar_out', '_outf', opname)
    opname = re.sub('\.Tensor', '', opname)
    opname = re.sub('_?\.to', '', opname)
    opname = re.sub('_?\.from', '', opname)
    opname = re.sub('\.Scalar', '', opname)
    opname = re.sub('\.self', '', opname)
    opname = re.sub('\.values_stable', '_outf', opname)
    opname = re.sub('\.values', '_outf', opname)
    opname = re.sub('\.grad_input', '_outf', opname)
    opname = re.sub('\.dim_max', '_outf', opname)
    opname = re.sub('\.dim_min', '_outf', opname)
    opname = re.sub('\.correction', '', opname)
    opname = re.sub('\.input', '', opname)
    opname = opname.replace('.', '_')
    opname = opname.split('.')[0]
    if opname[-1] == '_':
        opname = opname[0:len(opname) - 1]

    sym_int_array_params = re.findall('[ ,\)]?SymInt\[\d?\] *([\w\d_]+)', schema)
    if len(sym_int_array_params) > 0:
        sym_int_process_code = create_int_array_process_code(sym_int_array_params) + '\n'
    else:
        sym_int_process_code = ''

    code = 'auto ' + ' result_cpu = at::' + opname + '(' + create_args_name_list_from_schema(schema) + ');'
    for sym_int_param in sym_int_array_params:
        code = code.replace(sym_int_param, sym_int_param + 'Vector')

    code = sym_int_process_code + code

    sym_int_params = re.findall('[ ,\)]?SymInt\ *([\w\d_]+)', schema)
    for sym_int_param in sym_int_params:
        code = re.sub('([ ,\(])?' + sym_int_param + '([, \)])?', R'\1' + sym_int_param + R'.expect_int()\2', code)


    inputs = re.findall('Tensor +([\w\d_]+)', schema[:schema.find('->')])
    optional_inputs = re.findall('Tensor *\? +([\w\d_]+)', schema[:schema.find('->')])
    outputs = re.findall('Tensor\([a-z]!\)[ ]+([\w\d_]+){1}', schema[:schema.find('->')])
    tensors_arrays = re.findall('Tensor *\[ *\] * +([\w\d_]+)', schema[:schema.find('->')])
    tensors_arrays += re.findall('ITensorListRef *&? +([\w\d_]+)', schema[:schema.find('->')])
    optional_tensor_list_inputs = re.findall('Tensor *\? *\[ *\] +([\w\d_]+)', schema[:schema.find('->')])
    for input in inputs + optional_inputs + outputs + tensors_arrays + optional_tensor_list_inputs:
        code = re.sub('([\(, ]+)' + input + '([, \)]+)', R'\1' + input + '_cpu' + R'\2', code)

    return code

def create_call_dipu_cpp_function_code_from_schema(schema):
    code = create_return_code_frome_schema(schema) + ' result_device = ' + create_call_cpp_function_code_from_schema(schema).replace('; ', ';\n')
    return code.replace('; ', ';\n')

def create_result_compare_code(fun_config):
    schema = fun_config['schema']
    op_name = get_op_name_from_schema(fun_config['schema'])
    return_param = get_function_return_param_from_schema(fun_config['schema'])
    code = ''
    if len(return_param) == 1 :
        compare_code = f'_allclose(result_cpu, result_device)'
        code += f'std::cout << "autocompare:\t{op_name}\t{return_param[0]}:" << std::endl << "\t" << dumpArg(result_cpu) << std::endl << "\t" << dumpArg(result_device) << std::endl << "\t" << {compare_code} << std::endl;\n';
    elif len(return_param) > 1:
        for i in range(len(return_param)):
            compare_code = f'_allclose(std::get<{i}>(result_cpu), std::get<{i}>(result_device))'
            code += f'std::cout << "autocompare:\t{op_name}\t{return_param[i]}:" << std::endl << "\t" << dumpArg(std::get<{i}>(result_cpu)) << std::endl << "\t" << dumpArg(std::get<{i}>(result_device)) << std::endl << "\t" << {compare_code} << std::endl;\n';

    inputs = re.findall('Tensor +([\w\d_]+)', schema[:schema.find('->')])
    for i in range(len(inputs)):
        compare_code = f'_allclose({inputs[i]}_cpu, {inputs[i]})'
        code += f'std::cout << "autocompare:\t{op_name}\t{inputs[i]}: " << {compare_code} << std::endl;\n';

    return code;


def create_code_to_print_fun_call_info_from_schema(fun_config):
    op_name = get_op_name_from_schema(fun_config['schema'])
    diopi_func = fun_config.get('interface', '')
    diopi_func = diopi_func[0 : diopi_func.find('(')]
    debug_code = "if (dumpOpArgLevel() > 0) {\n\t"
    debug_code += f'printf("[%s:%d]:%s  %s \\n",__FUNCTION__,__LINE__,"{op_name}", "{diopi_func}");' + '\n'
    debug_code += "}\n"
    return debug_code

def create_int_array_process_code(int_array_list):
    if len(int_array_list) <= 0:
        return ''
    code = R"auto symIntToInt = [](const c10::SymInt& t)-> int64_t {return t.expect_int();};" + '\n'
    for int_array in int_array_list:
        code += f"std::vector<int64_t> {int_array}Vector({int_array}.size());\n"
        code += f"std::transform({int_array}.cbegin(), {int_array}.cend(), {int_array}Vector.begin(), symIntToInt);\n"
        code += f"::diopiSize_t {int_array}DiopiSize({int_array}Vector.data(), {int_array}Vector.size());\n"
    return code;

def create_autograd_function_name(op_name):
    op_name = 'Dipu' + op_name[0].upper() + op_name[1:]
    for patten in re.findall('[_\.][a-z]{1}', op_name):
        op_name = op_name.replace(patten, patten[1].upper())
    op_name = op_name.replace('_', 'Inp')
    return op_name + 'Function'

def create_save_for_backward_code(args_name_list):
    code = ''
    for arg_name in args_name_list:
        code += f'ctx->saved_data[\"{arg_name}\"] = {arg_name};\n'
    return code

def create_get_saved_data_code(args_name_list):
    code = ''
    for arg_name in args_name_list:
        code += f'auto {arg_name}_ = ctx->saved_data[\"{arg_name}\"];\n'
    return code

def create_optional_scalar_process_code(arg_name):
    process_template = CodeTemplate(
"""
::diopiScalar_t ${arg_name}DiopiScalar;
const ::diopiScalar_t* ${arg_name}DiopiScalarPtr = nullptr;
if ($arg_name.has_value()) {
    ${arg_name}DiopiScalar = dipu::diopi_helper::toDiopiScalar(${arg_name}.value());
    ${arg_name}DiopiScalarPtr = &${arg_name}DiopiScalar;
}
"""
    )
    process_code = process_template.substitute(
        arg_name=[arg_name],
    )
    return process_code



file_template = CodeTemplate(diopi_wrapper_file_template_content)

fun_template = CodeTemplate(diopi_wrapper_function_template_content)

op_register_template = CodeTemplate(op_register_template_content)

op_with_custom_fallback_register_template = CodeTemplate(op_with_custom_fallback_register_template_content)

custom_autograd_template = CodeTemplate(custom_autograd_template_content)

autocompare_template = CodeTemplate(autocompare_template_content)


def functions_code_gen(fun_config):
    if 'interface' in fun_config:
        diopi_fun_call_code = fun_config['interface'] + ";"
    else:
        diopi_interface = create_call_diop_interface_code_from_schema(fun_config['schema'])
        diopi_fun_call_code = diopi_interface + ';'

    input_process_code = ""
    diopi_tensor_suffix = 'DiopiTensorHandle'

    for input in set(get_function_inputs_from_schema(fun_config['schema']) + fun_config.get('ins', [])):
        if input.strip().endswith('?'):
            input = input.replace('?', '')
            input_process_code += f"\n::diopiConstTensorHandle_t {input}{diopi_tensor_suffix} = nullptr;\n"
            input_process_code += f"if ({input}.has_value() && {input}.value().defined()) {input}{diopi_tensor_suffix} = dipu::diopi_helper::toDiopiTensorHandle({input}.value());\n\n"
        else:
            input_process_code += f"::diopiConstTensorHandle_t {input}{diopi_tensor_suffix} = dipu::diopi_helper::toDiopiTensorHandle({input});\n"

        diopi_fun_call_code = re.sub(input.strip() + '([,\) ]{1})', f"{input.strip()}{diopi_tensor_suffix}" + r'\1', diopi_fun_call_code)

    diopi_size_suffix = 'DiopiSize'
    for size_attr in fun_config.get('size_attr', []):
        input_process_code += f"::diopiSize_t {size_attr}DiopiSize = dipu::diopi_helper::toDiopiSize({size_attr});\n"
        diopi_fun_call_code = re.sub(size_attr.strip() + '([,\) ]{1})', f"{size_attr.strip()}{diopi_size_suffix}" + r'\1', diopi_fun_call_code)


    output_process_code = ""
    for output in set(get_function_outputs_from_schema(fun_config['schema']) + fun_config.get('outs', [])):
        output_process_code += f"::diopiTensorHandle_t {output}{diopi_tensor_suffix} = dipu::diopi_helper::toDiopiTensorHandle({output});\n"
        diopi_fun_call_code = re.sub('([\(,& ]{1})' + output.strip() + '([,\) ]{1})', r'\1' + f"{output.strip()}{diopi_tensor_suffix}" + r'\2', diopi_fun_call_code)

    attrs_process_code = ""

    diopi_scalar_suffix = 'DiopiScalar'
    for scalar_param in get_function_scalar_args_from_schema(fun_config['schema']):
        attrs_process_code += f"::diopiScalar_t {scalar_param}{diopi_scalar_suffix} = dipu::diopi_helper::toDiopiScalar({scalar_param});\n";
        #diopi_fun_call_code = re.sub('&?[ ]*' + scalar_param.strip(), f"&{scalar_param}{diopi_scalar_suffix}", diopi_fun_call_code)
        diopi_fun_call_code = re.sub('([,\(]) *&? *' + scalar_param + '([,\)])', R'\1' + f"&{scalar_param}{diopi_scalar_suffix}" + R'\2', diopi_fun_call_code)

    cppsignature_template = CodeTemplate("$return_code $fun_name($param_list)")
    for scalar_param in get_function_optional_scalar_args_from_schema(fun_config['schema']):
        attrs_process_code += create_optional_scalar_process_code(scalar_param)
        diopi_fun_call_code = re.sub('([,\(] *&? *)' + scalar_param.strip() + '( *[,\)])', R'\1' + f"{scalar_param}DiopiScalarPtr" + R'\2', diopi_fun_call_code)




    int_array_list = get_function_int_array_args_from_schema(fun_config['schema'])
    attrs_process_code += create_int_array_process_code(int_array_list)
    for int_array_param in int_array_list:
        diopi_fun_call_code = re.sub('([,\(] *&? *)' + int_array_param.strip() + '( *[,\)])', R'\1' + f"{int_array_param}DiopiSize" + R'\2', diopi_fun_call_code)


    if fun_config.get('print_func_call_info', False) == True:
        fun_config['custom_code_at_the_beginning'] = create_code_to_print_fun_call_info_from_schema(fun_config) + fun_config.get('custom_code_at_the_beginning', '')

    if fun_config.get('print_op_args', False) == True:
        fun_config['custom_code_before_call_diopi'] = fun_config.get('custom_code_before_call_diopi', '') + create_print_op_args_code(fun_config)

    if fun_config.get('use_diopi_adapter', False) == True:
        diopi_fun_call_code = "diopiadaptor::" + diopi_fun_call_code
    else:
        diopi_fun_call_code = "::" + diopi_fun_call_code

    if fun_config.get('dummy_call_diopi', False) in [True, 'True']:
        diopi_fun_call_code = f"::diopiSuccess;/*dummy_call_diopi: {diopi_fun_call_code}*/"

    return_code = ""
    return_param = get_function_return_param_from_schema(fun_config['schema'])
    if len(return_param) == 0:
        return_code = "return;\n"
    elif len(return_param) == 1:
        return_code = f"return {return_param[0]};\n"
    else:
        params = ''
        for i in range(len(return_param)):
            params += return_param[i]
            if i < len(return_param) - 1:
                params += ', '
        return_code = f"return std::tie({params});"

    custom_code_at_the_beginning = fun_config.get('custom_code_at_the_beginning', fun_config.get('custom_code', ''))
    custom_code_at_the_beginning = re.sub(';\s*$', ';\n',custom_code_at_the_beginning)

    fbody = fun_template.substitute(
            comment=[fun_config['schema']],
            cppsignautre=[create_cpp_signature_from_schema(fun_config['schema'])],
            custom_code_at_the_beginning=[custom_code_at_the_beginning],
            input_process_code=[input_process_code],
            attrs_process_code=[attrs_process_code],
            output_process_code=[output_process_code],
            custom_code_before_call_diopi = [fun_config.get('custom_code_before_call_diopi', '').replace('; ', ';\n')],
            diopi_fun_call_code=[diopi_fun_call_code],
            custom_code_before_return=[fun_config.get('custom_code_before_return', '').replace('; ', ';\n')],
            return_code=[return_code],
    )
    diopi_interface = fun_config.get('interface', create_call_diop_interface_code_from_schema(fun_config['schema']))

    fun_name = create_fun_name_from_schema(fun_config['schema'])
    raw_fun_name = fun_name

    if fun_config.get('autograd', False) == True:
        wrapper_fun_name = fun_name + '_wrapper'
        custom_autograd_function_code = custom_autograd_template.substitute(
            autograd_function_name=[create_autograd_function_name(get_op_name_from_schema(fun_config['schema']))],
            cppsignautre=[create_cpp_signature_from_schema(fun_config['schema']).replace(fun_name, wrapper_fun_name)],
            return_code=[create_return_code_frome_schema(fun_config['schema'], allow_return_ref = False)],
            save_for_backward_code=[create_save_for_backward_code(fun_config.get('saved_data',[]))],
            param_list=[create_param_list_from_schema(fun_config['schema'])],
            arg_name_list=[create_args_name_list_from_schema(fun_config['schema'])],
            call_forward_impl_code=[create_call_cpp_function_code_from_schema(fun_config.get('forward_schema', fun_config['schema'])).replace('; ', ';\n')],
            forward_process_code=[fun_config.get('forward_process_code','').replace('; ', ';\n')],
            load_saved_data_code=[create_get_saved_data_code(fun_config.get('saved_data',[]))],
            cal_grad_code=[fun_config.get('cal_grad_code', '').replace('; ', ';\n') + '/*' + fun_config.get('backward_schema','') + '*/'],
            call_backward_impl_code=[("auto result = " + create_call_cpp_function_code_from_schema(fun_config['backward_schema']).replace('; ', ';\n')) if 'backward_schema' in fun_config else ''],
            backward_return_code=[fun_config.get('backward_return_code', '').replace('; ', ';\n')],
            wrappter_custom_return=[fun_config.get('wrappter_custom_return', 'return result;')]
        )
        fbody += custom_autograd_function_code
        fun_name = wrapper_fun_name

    if fun_config.get('autocompare', False) in [True, 'True'] and fun_config.get('register_op', True) in [True, 'True']:
        auto_compare_fun_name = fun_name + '_autocompare'
        autocompare_code = autocompare_template.substitute(
            cppsignautre=[create_cpp_signature_from_schema(fun_config['schema']).replace(raw_fun_name, auto_compare_fun_name)],
            transform_input_to_cpu_code=[create_transform_input_to_cpu_code(fun_config)],
            execute_op_on_cpu_code=[create_call_aten_cpu_cpp_function_code_from_schema(fun_config['schema'])],
            comment=[fun_config['schema']],
            execute_op_on_device_code=[create_call_dipu_cpp_function_code_from_schema(fun_config['schema']).replace(raw_fun_name, fun_name)],
            transform_result_to_cpu_code=[],
            result_compare_code=[create_result_compare_code(fun_config) + "\nreturn result_device;\n"],
        )
        fbody += autocompare_code
        fun_name = auto_compare_fun_name

    if fun_config.get('custom_fallback', False) in ['False', False]:
        register_body = op_register_template.substitute(
                register_name=[get_op_name_from_schema(fun_config['schema'])],
                aten_fun_name=['dipu::native::' + fun_name],
                diopi_fun_name=[get_fun_name_from_cppsignature(diopi_interface).replace('diopi', '::diopi')],
        )
    else:
        register_body = op_with_custom_fallback_register_template.substitute(
                register_name=[get_op_name_from_schema(fun_config['schema'])],
                aten_fun_name=['dipu::native::' + fun_name],
                diopi_fun_name=[get_fun_name_from_cppsignature(diopi_interface).replace('diopi', '::diopi')],
                force_fallback=['false' if fun_config.get('force_fallback', False) in [False, 'False'] else 'true'],
                fallbackFunc=['dipu::native::' + 'custom_fallback_' + fun_name.replace('_autocompare', '')],

        )
    return fbody, register_body

def boolean_string(s):
    if s not in {'False', 'True'}:
        raise ValueError('Not a valid boolean string')
    return s == 'True'

def parase_args():
    import argparse
    parser = argparse.ArgumentParser(description='autogen diopi wrapper code')
    parser.add_argument('--config', type=str, default = 'diopi_functions.yaml', help='path to functions config file')
    parser.add_argument('--out', type=str, default = 'AutoGenedKernels.cpp', help='path to functions config file')
    parser.add_argument('--dummy_call_diopi', default=False, type=boolean_string, help='whether acctually call diopi interface')
    parser.add_argument('--use_diopi_adapter', default=True, type=boolean_string, help='whether use diopi adapter')
    parser.add_argument('--diopi_adapter_header', type=str, default = 'diopi_adapters.hpp', help='path to diopi adapter file')
    parser.add_argument('--print_func_call_info', default=False, type=boolean_string, help='whether generate code that prints function call information')
    parser.add_argument('--print_op_args', default=False, type=boolean_string, help='whether generate code that prints op args')
    parser.add_argument('--autocompare', default=False, type=boolean_string, help='whether generate code that compare device calculation results with cpu calculation results')
    parser.add_argument('--fun_config_dict', type=json.loads, default = dict(), help='fun config for all ops') # --fun_config_dict '{"register_op": "False", "dummy_call_diopi":"True"}'

    args = parser.parse_args()
    return args

def main():
    args = parase_args()

    with open(args.config) as diopi_functions_file:
        file_data = diopi_functions_file.read()
        funcs_config = yaml.load(file_data, Loader=yaml.FullLoader)


    functions_code = ''
    op_register_code = ''
    header_include_code = ''

    if args.use_diopi_adapter == True:
        if os.path.exists(args.diopi_adapter_header) == False:
            print(f"{args.diopi_adapter_header} not exists")
            args.use_diopi_adapter = False
        else:
            header_include_code += f'#include "{os.path.abspath(args.diopi_adapter_header)}"'

    autograd_op_register_code = ''

    for fun_config in funcs_config:
        mergeed_fun_config = dict(args.fun_config_dict)
        mergeed_fun_config.update(vars(args))
        mergeed_fun_config.update(fun_config)
        if 'device' in mergeed_fun_config:
            current_device = mergeed_fun_config.get('current_device', '')
            if current_device not in (mergeed_fun_config['device'] + ['all',]):
                create_for_this_device = 'all' in mergeed_fun_config['device']
                for device in mergeed_fun_config['device']:
                    if ('-' + device) == current_device:
                        create_for_this_device = False
                        break
                if create_for_this_device == False:
                    continue
            if ('-' + current_device) in (mergeed_fun_config['device']):
                continue

        fun_code, register_code = functions_code_gen(mergeed_fun_config)
        functions_code += fun_code
        if mergeed_fun_config.get('register_op', True) in [True, "True"]:
            if mergeed_fun_config.get('autograd', False) == True:
                autograd_op_register_code += register_code
            op_register_code += register_code

    autogened_file = file_template.substitute(
        functions_code=[functions_code],
        header_include_code=[header_include_code],
        op_register_code=[op_register_code],
        autograd_op_register_code=[autograd_op_register_code]
    )
    autogened_file = re.sub(R'\n{3,}', R'\n\n', autogened_file)
    autogened_file = re.sub('[ ]*,[ ]*', ', ', autogened_file)
    with open(args.out, 'w') as cpp_file:
        cpp_file.write(autogened_file)

    print(f"Successfully generate {args.out} according to the configuration file {args.config}")


if __name__ == "__main__":
    main()
