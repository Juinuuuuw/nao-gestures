"""Python 2/3 compatible, scoped ALLeds expression with per-channel restore."""
import math
import time
import uuid

class EyeResources(object):
    """Own only the two decorative eye resources for a bounded utterance."""
    RESOURCES=['Left eye leds','Right eye leds']

    def __init__(self,session,manager):
        self.session=session;self.manager=manager;self.name='NAOStudioEyes_'+uuid.uuid4().hex
        self.service_id=None;self.acquired=False;self.conflicts=0

    def onConflict(self,resource,owner):
        # Release belongs to STOP/finally, not to another conversational effect.
        self.conflicts+=1

    def acquire(self):
        self.service_id=self.session.registerService(self.name,self)
        try:
            self.manager.acquireResourcesTree(self.RESOURCES,self.name,'onConflict',0)
            self.acquired=True
        except Exception:
            try:self.manager.releaseResources(self.RESOURCES,self.name)
            finally:self.session.unregisterService(self.service_id);self.service_id=None
            raise

    def release(self):
        try:
            if self.acquired:
                self.manager.releaseResources(self.RESOURCES,self.name)
                self.acquired=False
        finally:
            if self.service_id is not None:self.session.unregisterService(self.service_id);self.service_id=None

class EyeExpression(object):
    def __init__(self,leds,color):
        if isinstance(color,bool) or not isinstance(color,int) or not 0<=color<=0xFFFFFF:
            raise ValueError('Invalid eye color')
        self.leds=leds;self.color=color;self.original={};self.active=False;self.last_update=None;self.refresh_count=0;self.pending_until=0.

    def prepare(self):
        names=self.leds.listGroup('FaceLeds')
        if not names or len(names)>64 or any(not name.startswith('Face/Led/') for name in names):
            raise RuntimeError('Unexpected face LED channels')
        for name in names:
            value=float(self.leds.getIntensity(name))
            if math.isnan(value) or math.isinf(value) or not 0.<=value<=1.:raise RuntimeError('Invalid LED intensity')
            self.original[name]=value

    def start(self,now=None):
        if not self.original:self.prepare()
        try:self.leds.fadeRGB('FaceLeds',self.color,.12)
        except Exception:
            self.restore();raise
        self.active=True;self.last_update=time.time() if now is None else now
        self.pending_until=time.time()+.12

    def maintain(self,now=None):
        """Refresh only our face color at 2 Hz; never resnapshot overwritten blue."""
        now=time.time() if now is None else now
        if not self.active or now-self.last_update<.5:return False
        try:self.leds.fadeRGB('FaceLeds',self.color,.05)
        except Exception:
            self.active=False;raise
        self.last_update=now;self.refresh_count+=1
        self.pending_until=time.time()+.05
        return True

    def restore(self):
        self.active=False
        remaining=self.pending_until-time.time()
        if remaining>0:time.sleep(min(.13,remaining))
        errors=[]
        for name,value in self.original.items():
            try:self.leds.setIntensity(name,value)
            except Exception as error:errors.append(str(error))
        if errors:raise RuntimeError('Eye restoration failed: '+'; '.join(errors))
        self.original={}
