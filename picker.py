#!/usr/bin/python3
"""Native live Wayland eyedropper. Screen pixels remain in anonymous memory."""
import gi
for name,version in [('Gtk','3.0'),('Gdk','3.0'),('GtkLayerShell','0.1')]:gi.require_version(name,version)
from gi.repository import Gtk,Gdk,Gio,GLib,GdkPixbuf,GtkLayerShell as Layer
import cairo,ctypes,json,threading,signal,os,sys,time,math,logging
from pathlib import Path
ROOT=Path(__file__).parent
STATE=Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'okayu-color-picker/selection.json'
def hex_color(value):return f'#{value:06X}'
def color_rgb(value):return ((value>>16&255)/255,(value>>8&255)/255,(value&255)/255)
def load_selection():
 try:
  value=json.loads(STATE.read_text())['hex'];return int(value.lstrip('#'),16) if len(value)==7 and value.startswith('#') else None
 except (OSError,ValueError,KeyError,TypeError):return None

def cursor_image(value):
 # This is a cursor surface, not part of the captured desktop buffer.
 surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,72,72);cr=cairo.Context(surface)
 for width,color in [(10,(0,0,0)),(8,(1,1,1)),(5,color_rgb(value))]:
  cr.set_source_rgb(*color);cr.set_line_width(width);cr.arc(36,36,24,0,math.tau);cr.stroke()
 # Outlined pipette with its sampling tip exactly at the cursor hotspot.
 cr.move_to(36,36);cr.line_to(48,24);cr.set_source_rgb(.03,.02,.05);cr.set_line_cap(cairo.LINE_CAP_ROUND);cr.set_line_width(9);cr.stroke()
 cr.move_to(36,36);cr.line_to(48,24);cr.set_source_rgb(.95,.92,.98);cr.set_line_width(5);cr.stroke()
 cr.move_to(44,21);cr.line_to(51,28);cr.set_source_rgb(.03,.02,.05);cr.set_line_width(5);cr.stroke()
 pixbuf=Gdk.pixbuf_get_from_surface(surface,0,0,72,72)
 return Gdk.Cursor.new_from_pixbuf(Gdk.Display.get_default(),pixbuf,36,36)

class CaptureWorker(threading.Thread):
 def __init__(self,app,generation):
  super().__init__(daemon=True);self.app=app;self.generation=generation;self.stop_event=threading.Event();self.lock=threading.Lock();self.position=None;self.picks=[]
 def move(self,name,x,y):
  with self.lock:self.position=(name,x,y)
 def pick(self,name,x,y):
  with self.lock:self.picks.append((name,x,y));self.position=(name,x,y)
 def run(self):
  ctx=None
  try:
   lib=ctypes.CDLL(str(ROOT/'libpixel-capture.so'));lib.pixel_open.restype=ctypes.c_void_p
   lib.pixel_outputs.argtypes=[ctypes.c_void_p];lib.pixel_outputs.restype=ctypes.c_char_p
   lib.pixel_origin.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.POINTER(ctypes.c_int)]
   lib.pixel_refresh.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
   lib.pixel_read.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_double,ctypes.c_double,ctypes.POINTER(ctypes.c_uint32)]
   lib.pixel_close.argtypes=[ctypes.c_void_p]
   ctx=lib.pixel_open()
   if not ctx:raise RuntimeError('COSMIC does not expose the required capture protocol in this session.')
   outputs={}
   for name in lib.pixel_outputs(ctx).splitlines():
    origin=(ctypes.c_int*2)();lib.pixel_origin(ctx,name,origin)
    if lib.pixel_refresh(ctx,name)!=0:raise RuntimeError('Could not capture output '+name.decode())
    outputs[tuple(origin)]=name.decode()
   GLib.idle_add(self.app.capture_ready,self.generation,outputs)
   while not self.stop_event.is_set():
    with self.lock:
     selected=self.picks.pop(0) if self.picks else None;position=selected or self.position
    if position:
     name,x,y=position;encoded=name.encode();result=lib.pixel_refresh(ctx,encoded);value=ctypes.c_uint32()
     if result==0 and lib.pixel_read(ctx,encoded,x,y,ctypes.byref(value))==0:
      GLib.idle_add(self.app.sample_ready,self.generation,name,value.value,bool(selected))
     elif result not in (0,-5):raise RuntimeError('The output is no longer available. Reactivate the eyedropper.')
    self.stop_event.wait(.035)
  except Exception as error:GLib.idle_add(self.app.capture_error,self.generation,str(error))
  finally:
   if ctx:lib.pixel_close(ctx)

class Overlay(Gtk.Window):
 def __init__(self,app,monitor,name):
  super().__init__(type=Gtk.WindowType.TOPLEVEL);self.app=app;self.monitor=monitor;self.output_name=name;self.set_decorated(False);self.set_app_paintable(True);self.set_visual(self.get_screen().get_rgba_visual())
  Layer.init_for_window(self);Layer.set_namespace(self,'okayu-eyedropper');Layer.set_monitor(self,monitor);Layer.set_layer(self,Layer.Layer.OVERLAY);Layer.set_exclusive_zone(self,-1)
  for edge in [Layer.Edge.TOP,Layer.Edge.BOTTOM,Layer.Edge.LEFT,Layer.Edge.RIGHT]:Layer.set_anchor(self,edge,True)
  Layer.set_keyboard_mode(self,Layer.KeyboardMode.EXCLUSIVE)
  self.add_events(Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.ENTER_NOTIFY_MASK|Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.KEY_PRESS_MASK)
  self.connect('draw',self.draw);self.connect('motion-notify-event',self.motion);self.connect('enter-notify-event',self.motion);self.connect('button-press-event',self.press);self.connect('key-press-event',self.key)
  self.connect('realize',lambda *_:self.update_cursor());self.show_all()
 def draw(self,widget,cr):
  cr.set_operator(cairo.OPERATOR_SOURCE);cr.set_source_rgba(0,0,0,0);cr.paint();return True
 def update_cursor(self):
  if self.get_window():self.get_window().set_cursor(self.app.cursor)
 def normalized(self,event):
  return max(0,min(.999999,event.x/max(1,self.get_allocated_width()))),max(0,min(.999999,event.y/max(1,self.get_allocated_height())))
 def motion(self,widget,event):
  self.app.current_output=self.output_name;x,y=self.normalized(event)
  if self.app.worker:self.app.worker.move(self.output_name,x,y)
  self.update_cursor();return True
 def press(self,widget,event):
  if event.button==1:
   x,y=self.normalized(event)
   if self.app.worker:self.app.worker.pick(self.output_name,x,y)
   return True
  if event.button==3:self.app.stop();return True
  return True
 def key(self,widget,event):
  if event.keyval==Gdk.KEY_Escape:self.app.stop()
  return True

class ColorCard(Gtk.Window):
 def __init__(self,app,monitor):
  super().__init__(type=Gtk.WindowType.TOPLEVEL);self.app=app;self.value=0;self.set_decorated(False);self.set_resizable(False);self.set_app_paintable(False);self.set_visual(self.get_screen().get_rgba_visual());self.get_style_context().add_class('color-card')
  Layer.init_for_window(self);Layer.set_namespace(self,'okayu-color-selection');Layer.set_layer(self,Layer.Layer.OVERLAY);Layer.set_monitor(self,monitor);Layer.set_exclusive_zone(self,-1);Layer.set_anchor(self,Layer.Edge.TOP,True);Layer.set_anchor(self,Layer.Edge.RIGHT,True);Layer.set_margin(self,Layer.Edge.TOP,44);Layer.set_margin(self,Layer.Edge.RIGHT,24);Layer.set_keyboard_mode(self,Layer.KeyboardMode.ON_DEMAND)
  box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);box.set_border_width(16);self.add(box)
  header=Gtk.Box(spacing=12);label=Gtk.Label(label='Selected color');label.set_xalign(0);header.pack_start(label,True,True,0)
  close=Gtk.Button.new_from_icon_name('window-close-symbolic',Gtk.IconSize.BUTTON);close.set_relief(Gtk.ReliefStyle.NONE);close.set_tooltip_text('Close this color window');close.connect('clicked',lambda *_:self.destroy());header.pack_end(close,False,False,0);box.pack_start(header,False,False,0)
  row=Gtk.Box(spacing=14);self.swatch=Gtk.DrawingArea();self.swatch.set_size_request(76,76);self.swatch.connect('draw',self.draw_swatch);row.pack_start(self.swatch,False,False,0)
  right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);self.entry=Gtk.Entry();self.entry.set_editable(False);self.entry.set_width_chars(9);self.entry.get_style_context().add_class('color-code');right.pack_start(self.entry,False,False,0)
  self.copy_button=Gtk.Button(label='Copy HEX');self.copy_button.connect('clicked',self.copy_color);right.pack_start(self.copy_button,False,False,0);row.pack_start(right,True,True,0);box.pack_start(row,False,False,0)
  self.hint=Gtk.Label(label='Super+Alt+8: toggle eyedropper');self.hint.get_style_context().add_class('color-hint');box.pack_start(self.hint,False,False,0)
  self.add_events(Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.ENTER_NOTIFY_MASK);self.connect('motion-notify-event',self.hover);self.connect('enter-notify-event',self.hover)
  self.connect('destroy',self.closed);self.connect('realize',lambda *_:self.update_cursor());self.set_size_request(330,-1)
 def hover(self,widget,event):
  if not self.app.active or not self.app.worker:return False
  monitor=Layer.get_monitor(self);g=monitor.get_geometry();name=self.app.output_map.get((g.x,g.y))
  if not name:return False
  source=Gtk.get_event_widget(event)
  x,y=event.x,event.y
  if source and source is not self:
   translated=source.translate_coordinates(self,int(x),int(y))
   if translated:x,y=translated
  x=(g.width-24-self.get_allocated_width()+x)/g.width;y=(44+y)/g.height
  self.app.current_output=name;self.app.worker.move(name,max(0,min(.999999,x)),max(0,min(.999999,y)));return False
 def draw_swatch(self,widget,cr):
  cr.set_source_rgb(*color_rgb(self.value));cr.rectangle(0,0,widget.get_allocated_width(),widget.get_allocated_height());cr.fill();return True
 def set_color(self,value):
  self.value=value;self.entry.set_text(hex_color(value));self.swatch.queue_draw();self.copy_button.set_label('Copy HEX')
 def update_cursor(self):
  if self.get_window():self.get_window().set_cursor(self.app.cursor if self.app.active else None)
 def copy_color(self,*_):
  clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD);clipboard.set_text(hex_color(self.value),-1);clipboard.store();self.copy_button.set_label('Copied')
 def closed(self,*_):
  if self.app.card is self:self.app.card=None

class App(Gtk.Application):
 def __init__(self):
  super().__init__(application_id='local.okayu.ColorPicker',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE);self.active=False;self.worker=None;self.generation=0;self.overlays=[];self.card=None;self.selected=load_selection();self.current_output=None;self.cursor=None;self.output_map={}
 def do_startup(self):
  Gtk.Application.do_startup(self);self.hold();self.css=Gtk.CssProvider();self.css.load_from_data(b'window.color-card { background-color: #241b33; color: #eee7f5; border: 1px solid #9381a3; border-radius: 12px; } .color-card label, .color-card button { color: #eee7f5; } .color-card entry { color: #eee7f5; background-color: #15111e; } .color-card .color-code { font: bold 16pt monospace; } .color-card .color-hint { color: #c7b7e6; font-size: 9pt; }');Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),self.css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+40)
 def toggle(self):
  if self.active:self.stop()
  else:
   self.active=True;self.generation+=1;self.cursor=cursor_image(self.selected if self.selected is not None else 0xA785D8);self.worker=CaptureWorker(self,self.generation);self.worker.start()
 def stop(self):
  self.active=False;self.generation+=1
  if self.worker:self.worker.stop_event.set();self.worker=None
  for window in self.overlays:window.destroy()
  self.overlays=[];self.current_output=None
  if self.card:self.card.update_cursor()
 def capture_ready(self,generation,outputs):
  if not self.active or generation!=self.generation:return False
  self.output_map=outputs;display=Gdk.Display.get_default()
  for i in range(display.get_n_monitors()):
   monitor=display.get_monitor(i);g=monitor.get_geometry();name=outputs.get((g.x,g.y))
   if name:self.overlays.append(Overlay(self,monitor,name))
  if not self.overlays:self.capture_error(generation,'Could not match monitors to COSMIC capture outputs.')
  elif self.card:self.card.hide();self.card.show_all();self.card.update_cursor()
  return False
 def sample_ready(self,generation,name,value,picked):
  if not self.active or generation!=self.generation:return False
  if name==self.current_output or picked:
   self.cursor=cursor_image(value)
   for overlay in self.overlays:overlay.update_cursor()
   if self.card:self.card.update_cursor()
  if picked:
   monitor=next((w.monitor for w in self.overlays if w.output_name==name),Gdk.Display.get_default().get_monitor(0));self.show_color(value,monitor)
  return False
 def show_color(self,value,monitor=None):
  self.selected=value;STATE.parent.mkdir(parents=True,exist_ok=True);STATE.write_text(json.dumps({'hex':hex_color(value)})+'\n')
  if not self.card:self.card=ColorCard(self,monitor or Gdk.Display.get_default().get_monitor(0))
  self.card.set_color(value);self.card.show_all();self.card.update_cursor()
 def capture_error(self,generation,message):
  if generation!=self.generation:return False
  self.stop();logging.error('%s',message);dialog=Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,buttons=Gtk.ButtonsType.CLOSE,text='Could not activate the eyedropper');dialog.format_secondary_text(message);dialog.connect('response',lambda d,*_:d.destroy());dialog.show_all();return False
 def do_command_line(self,command):
  args=command.get_arguments()[1:]
  if '--quit' in args:self.stop();self.quit()
  elif '--status' in args:command.print_literal(json.dumps({'active':self.active,'overlays':len(self.overlays),'selected':None if self.selected is None else hex_color(self.selected),'window_open':self.card is not None})+'\n')
  elif '--idle' in args:pass
  elif '--show-color' in args:
   try:
    value=int(args[args.index('--show-color')+1].lstrip('#'),16)
    if not 0<=value<=0xFFFFFF:return 2
    self.show_color(value)
   except (ValueError,IndexError):return 2
  else:self.toggle()
  return 0
 def do_shutdown(self):
  self.stop()
  if self.card:self.card.destroy()
  Gtk.Application.do_shutdown(self)
if __name__=='__main__':
 logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s');app=App();signal.signal(signal.SIGTERM,lambda *_:GLib.idle_add(app.quit));sys.exit(app.run(sys.argv))
