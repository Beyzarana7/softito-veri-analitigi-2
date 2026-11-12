"""HiGHS 1.15 callback ve API durum kaydı; arama seçeneklerini değiştirmez."""
import json
import math
from pathlib import Path
import time


def scalar(value):
    if value is None:return None
    if isinstance(value,str):return value
    try:
        f=float(value)
        if not math.isfinite(f):return None
        return int(f) if isinstance(value,int) else f
    except (TypeError,ValueError):return str(value)


class Recorder:
    def __init__(self,folder=None):
        self.folder=None if folder is None else Path(folder)
        self.events=[];self.options={};self.api={};self.errors=[];self.start=time.perf_counter()
        self.counts={'mip_solution':0,'mip_improving_solution':0,'mip_logging':0}
        self.final_info={}

    def event(self,kind,**values):
        self.events.append(dict(event=kind,wall_seconds=time.perf_counter()-self.start,**values))

    def attach(self,solver):
        def handler(kind):
            def record(event):
                try:
                    self.counts[kind]+=1
                    data=event.data_out
                    fields=['running_time','mip_primal_bound','mip_dual_bound','mip_gap','mip_node_count',
                            'simplex_iteration_count','ipm_iteration_count','objective_function_value']
                    self.event(kind,message=event.message,**{n:scalar(getattr(data,n,None)) for n in fields})
                except Exception as error:self.errors.append(type(error).__name__+': '+str(error))
            return record
        solver.cbMipSolution.subscribe(handler('mip_solution'))
        solver.cbMipImprovingSolution.subscribe(handler('mip_improving_solution'))
        solver.cbMipLogging.subscribe(handler('mip_logging'))
        self.event('callbacks_attached')

    def options_at(self,solver,stage):
        self.options[stage]={name:{'status':str((result:=solver.getOptionValue(name))[0]),'value':scalar(result[1])}
                             for name in ['random_seed','threads','time_limit','mip_rel_gap']}
        self.event('options',stage=stage,values=self.options[stage])

    def api_status(self,name,status,**values):
        self.api[name]=str(status);self.event('api_status',name=name,status=str(status),**values)

    def final(self,solver):
        info=solver.getInfo()
        names=['valid','objective_function_value','mip_dual_bound','mip_gap','mip_node_count',
               'simplex_iteration_count','ipm_iteration_count','primal_dual_integral','primal_solution_status',
               'max_primal_infeasibility','max_integrality_violation']
        self.final_info={n:scalar(getattr(info,n,None)) for n in names}
        self.final_info['model_status']=solver.modelStatusToString(solver.getModelStatus())
        self.event('final_info',**self.final_info)

    def summary(self):
        text=''
        if self.folder is not None and (self.folder/'solver_trace.txt').exists():
            text=(self.folder/'solver_trace.txt').read_text(encoding='utf-8',errors='replace')
        return dict(api_status=self.api,options=self.options,event_counts=self.counts,callback_errors=self.errors,
             final_info=self.final_info,native_mip_start_feasible_message=('MIP start solution is feasible' in text),
             feasible_solution_count=None,solution_count_note='Callback events are not a certified count of unique feasible solutions.')

    def finish(self):
        if self.folder is None:return
        self.folder.mkdir(parents=True,exist_ok=True)
        with (self.folder/'solver_events.jsonl').open('w',encoding='utf-8') as handle:
            for event in self.events:handle.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n')
        (self.folder/'solver_diagnostics.json').write_text(json.dumps(self.summary(),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
