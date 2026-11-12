"""Mevcut tam MILP'yi değiştirmeden aday vektörünü bütün satırlarında sınar.

AST kesimi yalnız matrisi/aday vektörünü dışarı verir; HiGHS oluşturulmaz.
"""
import ast
import hashlib
import importlib.util
from pathlib import Path

import numpy as np


def load_builder(source):
    source=Path(source)
    spec=importlib.util.spec_from_file_location('audit_original_solver',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    tree=ast.parse(source.read_text(encoding='utf-8'))
    function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='firma_cizelgele')
    function.name='build_candidate'
    kept=[];economic_guard=0;cut=0
    for node in function.body:
        # Karşılaştırma amacı olmayan fizibilite denetiminde pahalı aday da sınanabilir.
        if isinstance(node,ast.If) and any(isinstance(n,ast.Constant) and n.value=='Başlangıç çözümü referanstan daha pahalı olamaz.' for n in ast.walk(node)):
            economic_guard+=1;continue
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='denetle' and len(node.value.args)==1 and isinstance(node.value.args[0],ast.Name) and node.value.args[0].id=='warm':
            fields=['A','c','lo','hi','lb','ub','integer','warm','sabit_bedel','etiket','adlar','bas_ozet']
            kept.append(ast.Return(value=ast.Dict(keys=[ast.Constant(x) for x in fields],values=[ast.Name(id=x,ctx=ast.Load()) for x in fields])))
            cut+=1;break
        kept.append(node)
    if economic_guard!=1 or cut!=1:raise ValueError('Beklenen kaynak yapısı değişmiş; güvenli kesim uygulanmadı.')
    function.body=kept
    code=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
    namespace=vars(module).copy();exec(compile(code,str(source)+'::candidate_only','exec'),namespace)
    return namespace['build_candidate'],dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
          optimization_calls=0,removed_nonphysical_cost_guard=1,cut_before='denetle(warm) / Highs creation')


def evaluate(matrix,expected_cost,tolerance=1e-5,objective_tolerance=.02):
    x=matrix['warm'];a=matrix['A']@x
    violations=[]
    for i in np.flatnonzero((a<matrix['lb']-tolerance)|(a>matrix['ub']+tolerance)):
        violations.append(dict(kind='constraint',index=int(i),label=matrix['etiket'][i],
           activity=float(a[i]),lower=None if not np.isfinite(matrix['lb'][i]) else float(matrix['lb'][i]),
           upper=None if not np.isfinite(matrix['ub'][i]) else float(matrix['ub'][i])))
    for i in np.flatnonzero((x<matrix['lo']-tolerance)|(x>matrix['hi']+tolerance)):
        violations.append(dict(kind='variable_bound',index=int(i),label=matrix['adlar'][i],value=float(x[i])))
    for i in np.flatnonzero(matrix['integer'] & (np.abs(x-np.round(x))>tolerance)):
        violations.append(dict(kind='integrality',index=int(i),label=matrix['adlar'][i],value=float(x[i])))
    objective=float(matrix['c']@x+matrix['sabit_bedel'])
    difference=objective-float(expected_cost)
    if abs(difference)>objective_tolerance:
        violations.append(dict(kind='objective_accounting',matrix_objective=objective,independent_cost=float(expected_cost),difference=difference))
    residual=np.maximum(np.maximum(matrix['lb']-a,a-matrix['ub']),0)
    return dict(full_model_feasible=not violations,rows_checked=int(len(a)),columns_checked=int(len(x)),
        fixed_prefix_columns=0,matrix_objective_tl=objective,
        independent_cost_tl=float(expected_cost),objective_difference_tl=difference,
        maximum_constraint_violation=float(residual.max()),violations=violations)


def assert_same_model(reference,candidate):
    for key in ['c','lo','hi','lb','ub','integer']:np.testing.assert_array_equal(reference[key],candidate[key])
    for key in ['indptr','indices','data']:np.testing.assert_array_equal(getattr(reference['A'],key),getattr(candidate['A'],key))
    assert reference['etiket']==candidate['etiket'] and reference['adlar']==candidate['adlar']
    assert reference['sabit_bedel']==candidate['sabit_bedel']


def tightened_regret(cost,lower,upper):
    if lower>upper+.02 or cost<lower-.02:raise ValueError('Geçersiz maliyet sınırları.')
    return max(0.,float(cost-upper)),max(0.,float(cost-lower))
