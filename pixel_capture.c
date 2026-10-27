#define _GNU_SOURCE
#include <wayland-client.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/poll.h>
#include <time.h>
#include "capture.h"
#include "source.h"
struct output {struct wl_output *wl; uint32_t id; char name[128]; uint32_t width,height,format,transform,buffer_width,buffer_height; int x,y; int constraints,stopped,ready,valid;struct ext_image_capture_source_v1 *source;struct ext_image_copy_capture_session_v1 *session;struct wl_buffer *buffer;void *pixels;size_t size;};
struct context {struct wl_display *display;struct wl_registry *registry;struct wl_shm *shm;struct ext_output_image_capture_source_manager_v1 *sources;struct ext_image_copy_capture_manager_v1 *capture;struct output outputs[16];int count;char names[2048];};
static void geometry(void*d,struct wl_output*w,int32_t x,int32_t y,int32_t pw,int32_t ph,int32_t sub,const char*m,const char*n,int32_t tr){struct output*o=d;o->x=x;o->y=y;}
static void mode(void*d,struct wl_output*w,uint32_t flags,int32_t width,int32_t height,int32_t refresh){}
static void done(void*d,struct wl_output*w){}
static void scale(void*d,struct wl_output*w,int32_t s){}
static void name(void*d,struct wl_output*w,const char*n){snprintf(((struct output*)d)->name,128,"%s",n);}
static void description(void*d,struct wl_output*w,const char*n){}
static const struct wl_output_listener output_listener={geometry,mode,done,scale,name,description};
static void global(void *data,struct wl_registry*r,uint32_t id,const char*interface,uint32_t version){struct context*c=data;
 if(!strcmp(interface,"wl_shm"))c->shm=wl_registry_bind(r,id,&wl_shm_interface,1);
 else if(!strcmp(interface,"ext_output_image_capture_source_manager_v1"))c->sources=wl_registry_bind(r,id,&ext_output_image_capture_source_manager_v1_interface,1);
 else if(!strcmp(interface,"ext_image_copy_capture_manager_v1"))c->capture=wl_registry_bind(r,id,&ext_image_copy_capture_manager_v1_interface,1);
 else if(!strcmp(interface,"wl_output")&&c->count<16){struct output*o=&c->outputs[c->count++];o->id=id;o->format=UINT32_MAX;o->wl=wl_registry_bind(r,id,&wl_output_interface,version<4?version:4);wl_output_add_listener(o->wl,&output_listener,o);}}
static void removed(void*d,struct wl_registry*r,uint32_t id){struct context*c=d;for(int i=0;i<c->count;i++)if(c->outputs[i].id==id)c->outputs[i].stopped=1;}
static const struct wl_registry_listener registry_listener={global,removed};
static void buffer_size(void*d,struct ext_image_copy_capture_session_v1*s,uint32_t w,uint32_t h){struct output*o=d;if(o->width!=w||o->height!=h)o->valid=0;o->width=w;o->height=h;}
static void shm_format(void*d,struct ext_image_copy_capture_session_v1*s,uint32_t f){struct output*o=d;if((f==WL_SHM_FORMAT_ARGB8888||f==WL_SHM_FORMAT_XRGB8888||f==WL_SHM_FORMAT_ABGR8888||f==WL_SHM_FORMAT_XBGR8888)&&o->format==UINT32_MAX)o->format=f;}
static void dmabuf_device(void*d,struct ext_image_copy_capture_session_v1*s,struct wl_array*a){}
static void dmabuf_format(void*d,struct ext_image_copy_capture_session_v1*s,uint32_t f,struct wl_array*a){}
static void constraints(void*d,struct ext_image_copy_capture_session_v1*s){((struct output*)d)->constraints=1;}
static void stopped(void*d,struct ext_image_copy_capture_session_v1*s){((struct output*)d)->stopped=1;}
static const struct ext_image_copy_capture_session_v1_listener session_listener={buffer_size,shm_format,dmabuf_device,dmabuf_format,constraints,stopped};
static void transform(void*d,struct ext_image_copy_capture_frame_v1*f,uint32_t t){((struct output*)d)->transform=t;}
static void damage(void*d,struct ext_image_copy_capture_frame_v1*f,int32_t x,int32_t y,int32_t w,int32_t h){}
static void presentation(void*d,struct ext_image_copy_capture_frame_v1*f,uint32_t hi,uint32_t lo,uint32_t ns){}
static void ready(void*d,struct ext_image_copy_capture_frame_v1*f){struct output*o=d;o->ready=1;o->valid=1;}
static void failed(void*d,struct ext_image_copy_capture_frame_v1*f,uint32_t reason){((struct output*)d)->ready=-1;}
static const struct ext_image_copy_capture_frame_v1_listener frame_listener={transform,damage,presentation,ready,failed};
static int dispatch(struct context*c,int timeout){
 while(wl_display_prepare_read(c->display)!=0)if(wl_display_dispatch_pending(c->display)<0)return -1;
 wl_display_flush(c->display);struct pollfd fd={wl_display_get_fd(c->display),POLLIN,0};int r=poll(&fd,1,timeout);
 if(r>0&&(fd.revents&POLLIN)){if(wl_display_read_events(c->display)<0)return -1;return wl_display_dispatch_pending(c->display)<0?-1:1;}
 wl_display_cancel_read(c->display);return r<0?-1:0;}
void *pixel_open(void){struct context*c=calloc(1,sizeof(*c));if(!c)return NULL;c->display=wl_display_connect(NULL);if(!c->display){free(c);return NULL;}
 c->registry=wl_display_get_registry(c->display);wl_registry_add_listener(c->registry,&registry_listener,c);
 if(wl_display_roundtrip(c->display)<0||wl_display_roundtrip(c->display)<0||!c->shm||!c->sources||!c->capture){wl_display_disconnect(c->display);free(c);return NULL;}return c;}
const char *pixel_outputs(void*ctx){struct context*c=ctx;c->names[0]=0;for(int i=0;i<c->count;i++){if(i)strcat(c->names,"\n");strncat(c->names,c->outputs[i].name,sizeof(c->names)-strlen(c->names)-1);}return c->names;}
static struct output *find(struct context*c,const char*name){for(int i=0;i<c->count;i++)if(!strcmp(c->outputs[i].name,name))return &c->outputs[i];return NULL;}
int pixel_origin(void*ctx,const char*name,int*xy){struct output*o=find(ctx,name);if(!o)return -1;xy[0]=o->x;xy[1]=o->y;return 0;}
int pixel_refresh(void*ctx,const char*name){struct context*c=ctx;struct output*o=find(c,name);if(!o||o->stopped)return -1;
 if(!o->session){o->source=ext_output_image_capture_source_manager_v1_create_source(c->sources,o->wl);o->session=ext_image_copy_capture_manager_v1_create_session(c->capture,o->source,0);ext_image_copy_capture_session_v1_add_listener(o->session,&session_listener,o);
  for(int i=0;i<20&&!o->constraints&&!o->stopped;i++)if(dispatch(c,100)<0)return -2;}
 if(o->stopped||!o->constraints||o->format==UINT32_MAX||!o->width||!o->height||o->width>32768||o->height>32768)return -3;
 size_t size=(size_t)o->width*o->height*4;
 if(!o->buffer||o->size!=size||o->buffer_width!=o->width||o->buffer_height!=o->height){
  if(o->buffer)wl_buffer_destroy(o->buffer);if(o->pixels)munmap(o->pixels,o->size);o->pixels=NULL;o->buffer=NULL;
  int fd=memfd_create("okayu-pixel-buffer",MFD_CLOEXEC);if(fd<0||ftruncate(fd,size)<0){if(fd>=0)close(fd);return -4;}
  o->pixels=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);if(o->pixels==MAP_FAILED){o->pixels=NULL;close(fd);return -4;}
  struct wl_shm_pool*p=wl_shm_create_pool(c->shm,fd,size);o->buffer=wl_shm_pool_create_buffer(p,0,o->width,o->height,o->width*4,o->format);wl_shm_pool_destroy(p);close(fd);o->size=size;o->buffer_width=o->width;o->buffer_height=o->height;o->valid=0;}
 struct ext_image_copy_capture_frame_v1*frame=ext_image_copy_capture_session_v1_create_frame(o->session);ext_image_copy_capture_frame_v1_add_listener(frame,&frame_listener,o);o->ready=0;
 ext_image_copy_capture_frame_v1_attach_buffer(frame,o->buffer);ext_image_copy_capture_frame_v1_damage_buffer(frame,0,0,o->width,o->height);ext_image_copy_capture_frame_v1_capture(frame);
 for(int i=0;i<4&&!o->ready;i++){int r=dispatch(c,80);if(r<0){o->ready=-1;break;}if(r==0)break;}
 ext_image_copy_capture_frame_v1_destroy(frame);wl_display_flush(c->display);return o->valid?0:-5;}
int pixel_read(void*ctx,const char*name,double x,double y,uint32_t*color){struct output*o=find(ctx,name);if(!o||!o->valid||!o->pixels)return -1;
 double u=x,v=y;
 /* The protocol transform describes a transform already applied to the image. */
 switch(o->transform){case 1:u=y;v=1-x;break;case 2:u=1-x;v=1-y;break;case 3:u=1-y;v=x;break;case 4:u=1-x;break;case 5:u=1-y;v=1-x;break;case 6:v=1-y;break;case 7:u=y;v=x;break;}
 int px=(int)(u*o->width),py=(int)(v*o->height);if(px<0)px=0;if(py<0)py=0;if(px>=o->width)px=o->width-1;if(py>=o->height)py=o->height-1;
 uint32_t value=((uint32_t*)o->pixels)[(size_t)py*o->width+px];if(o->format==WL_SHM_FORMAT_ABGR8888||o->format==WL_SHM_FORMAT_XBGR8888)*color=((value&255)<<16)|(value&0xff00)|((value>>16)&255);else *color=value&0x00ffffff;return 0;}
void pixel_close(void*ctx){if(!ctx)return;struct context*c=ctx;for(int i=0;i<c->count;i++){struct output*o=&c->outputs[i];if(o->buffer)wl_buffer_destroy(o->buffer);if(o->session)ext_image_copy_capture_session_v1_destroy(o->session);if(o->source)ext_image_capture_source_v1_destroy(o->source);if(o->pixels)munmap(o->pixels,o->size);if(o->wl)wl_output_destroy(o->wl);}if(c->capture)ext_image_copy_capture_manager_v1_destroy(c->capture);if(c->sources)ext_output_image_capture_source_manager_v1_destroy(c->sources);if(c->shm)wl_shm_destroy(c->shm);if(c->registry)wl_registry_destroy(c->registry);wl_display_disconnect(c->display);free(c);}
