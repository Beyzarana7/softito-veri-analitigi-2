import json
from service import create_plan
if __name__=='__main__':
    try:
        folder=create_plan()
        print(json.dumps({'run_folder':str(folder),'success':True},ensure_ascii=True))
    except Exception as e:
        print(json.dumps({'success':False,'error':str(e)},ensure_ascii=True))
        raise SystemExit(1)
