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
#include <math.h>
#include "capture.h"
#include "source.h"
#include "workspace.h"
#include "cosmic-source.h"
struct context;
struct workspace_group {struct context *ctx;struct ext_workspace_group_handle_v1 *wl;uint32_t outputs;int removed;};
struct workspace_record {struct ext_workspace_handle_v1 *wl;struct workspace_group *group;int active,removed;};
struct output {struct wl_output *wl;uint32_t id;char name[128];uint32_t width,height,format,transform,buffer_width,buffer_height,buffer_format;int x,y;int constraints,stopped,ready,valid;struct ext_image_capture_source_v1 *source;struct ext_image_copy_capture_session_v1 *session;struct wl_buffer *buffer;void *pixels;size_t size;struct ext_workspace_handle_v1 *workspace;};
struct context {struct wl_display *display;struct wl_registry *registry;struct wl_shm *shm;struct ext_output_image_capture_source_manager_v1 *sources;struct ext_image_copy_capture_manager_v1 *capture;struct output outputs[16];int count;char names[2048];struct ext_workspace_manager_v1 *workspace_manager;struct zcosmic_workspace_image_capture_source_manager_v1 *workspace_sources;struct workspace_group groups[32];struct workspace_record workspaces[512];int group_count,workspace_count;uint32_t workspace_manager_id;};

static struct workspace_record *workspace_record(struct context *c,struct ext_workspace_handle_v1 *wl) {
 for(int i=0;i<c->workspace_count;i++)if(c->workspaces[i].wl==wl)return &c->workspaces[i];return NULL;
}
static void workspace_id(void*d,struct ext_workspace_handle_v1*w,const char*value){}
static void workspace_name(void*d,struct ext_workspace_handle_v1*w,const char*value){}
static void workspace_coordinates(void*d,struct ext_workspace_handle_v1*w,struct wl_array*value){}
static void workspace_state(void*d,struct ext_workspace_handle_v1*w,uint32_t state){((struct workspace_record*)d)->active=!!(state&EXT_WORKSPACE_HANDLE_V1_STATE_ACTIVE);}
static void workspace_capabilities(void*d,struct ext_workspace_handle_v1*w,uint32_t caps){}
static void workspace_removed(void*d,struct ext_workspace_handle_v1*w){struct workspace_record *record=d;record->removed=1;record->active=0;}
static const struct ext_workspace_handle_v1_listener workspace_listener={workspace_id,workspace_name,workspace_coordinates,workspace_state,workspace_capabilities,workspace_removed};
static void group_capabilities(void*d,struct ext_workspace_group_handle_v1*g,uint32_t caps){}
static void group_output_enter(void*d,struct ext_workspace_group_handle_v1*g,struct wl_output*output){struct workspace_group *group=d;for(int i=0;i<group->ctx->count;i++)if(group->ctx->outputs[i].wl==output)group->outputs|=1u<<i;}
static void group_output_leave(void*d,struct ext_workspace_group_handle_v1*g,struct wl_output*output){struct workspace_group *group=d;for(int i=0;i<group->ctx->count;i++)if(group->ctx->outputs[i].wl==output)group->outputs&=~(1u<<i);}
static void group_workspace_enter(void*d,struct ext_workspace_group_handle_v1*g,struct ext_workspace_handle_v1*workspace){struct workspace_group *group=d;struct workspace_record *record=workspace_record(group->ctx,workspace);if(record)record->group=group;}
static void group_workspace_leave(void*d,struct ext_workspace_group_handle_v1*g,struct ext_workspace_handle_v1*workspace){struct workspace_group *group=d;struct workspace_record *record=workspace_record(group->ctx,workspace);if(record&&record->group==group)record->group=NULL;}
static void group_removed(void*d,struct ext_workspace_group_handle_v1*g){struct workspace_group *group=d;group->removed=1;group->outputs=0;}
static const struct ext_workspace_group_handle_v1_listener group_listener={group_capabilities,group_output_enter,group_output_leave,group_workspace_enter,group_workspace_leave,group_removed};
static void manager_group(void*d,struct ext_workspace_manager_v1*m,struct ext_workspace_group_handle_v1*wl){struct context*c=d;if(c->group_count>=32)return;struct workspace_group*group=&c->groups[c->group_count++];group->ctx=c;group->wl=wl;ext_workspace_group_handle_v1_add_listener(wl,&group_listener,group);}
static void manager_workspace(void*d,struct ext_workspace_manager_v1*m,struct ext_workspace_handle_v1*wl){struct context*c=d;if(c->workspace_count>=512)return;struct workspace_record*record=&c->workspaces[c->workspace_count++];record->wl=wl;ext_workspace_handle_v1_add_listener(wl,&workspace_listener,record);}
static void manager_done(void*d,struct ext_workspace_manager_v1*m){}
static void manager_finished(void*d,struct ext_workspace_manager_v1*m){((struct context*)d)->workspace_manager=NULL;wl_proxy_destroy((struct wl_proxy*)m);}
static const struct ext_workspace_manager_v1_listener workspace_manager_listener={manager_group,manager_workspace,manager_done,manager_finished};
static struct ext_workspace_handle_v1 *active_workspace(struct context*c,struct output*output){unsigned index=output-c->outputs;for(int i=0;i<c->workspace_count;i++){struct workspace_record*r=&c->workspaces[i];if(r->active&&!r->removed&&r->group&&!r->group->removed&&(r->group->outputs&(1u<<index)))return r->wl;}return NULL;}

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
 else if(!strcmp(interface,"ext_workspace_manager_v1"))c->workspace_manager_id=id;
 else if(!strcmp(interface,"zcosmic_workspace_image_capture_source_manager_v1"))c->workspace_sources=wl_registry_bind(r,id,&zcosmic_workspace_image_capture_source_manager_v1_interface,1);
 else if(!strcmp(interface,"wl_output")&&c->count<16){struct output*o=&c->outputs[c->count++];o->id=id;o->format=UINT32_MAX;o->wl=wl_registry_bind(r,id,&wl_output_interface,version<4?version:4);wl_output_add_listener(o->wl,&output_listener,o);}}
static void removed(void*d,struct wl_registry*r,uint32_t id){struct context*c=d;for(int i=0;i<c->count;i++)if(c->outputs[i].id==id)c->outputs[i].stopped=1;}
static const struct wl_registry_listener registry_listener={global,removed};
static void buffer_size(void*d,struct ext_image_copy_capture_session_v1*s,uint32_t w,uint32_t h){struct output*o=d;if(o->width!=w||o->height!=h)o->valid=0;o->width=w;o->height=h;}
/* Prefer an opaque RGB buffer. The picker does not consume output alpha and
 * should not use an alpha-bearing readback when an opaque format is offered. */
static int format_rank(uint32_t format) {
 if(format==WL_SHM_FORMAT_XRGB8888)return 4;
 if(format==WL_SHM_FORMAT_XBGR8888)return 3;
 if(format==WL_SHM_FORMAT_ARGB8888)return 2;
 if(format==WL_SHM_FORMAT_ABGR8888)return 1;
 return 0;
}
static void shm_format(void*d,struct ext_image_copy_capture_session_v1*s,uint32_t f) {
 struct output *o=d;
 if(format_rank(f)>format_rank(o->format))o->format=f;
}
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
 if(wl_display_roundtrip(c->display)<0||wl_display_roundtrip(c->display)<0||!c->shm||!c->sources||!c->capture){wl_display_disconnect(c->display);free(c);return NULL;}
 /* Bind outputs first: COSMIC announces group-output links when the workspace
  * manager is bound, so those output resources must already exist. */
 if(c->workspace_manager_id&&c->workspace_sources){
  c->workspace_manager=wl_registry_bind(c->registry,c->workspace_manager_id,&ext_workspace_manager_v1_interface,1);
  ext_workspace_manager_v1_add_listener(c->workspace_manager,&workspace_manager_listener,c);
  if(wl_display_roundtrip(c->display)<0||wl_display_roundtrip(c->display)<0){wl_display_disconnect(c->display);free(c);return NULL;}
 }
 return c;}
const char *pixel_outputs(void*ctx){struct context*c=ctx;c->names[0]=0;for(int i=0;i<c->count;i++){if(i)strcat(c->names,"\n");strncat(c->names,c->outputs[i].name,sizeof(c->names)-strlen(c->names)-1);}return c->names;}
static struct output *find(struct context*c,const char*name){for(int i=0;i<c->count;i++)if(!strcmp(c->outputs[i].name,name))return &c->outputs[i];return NULL;}
int pixel_origin(void*ctx,const char*name,int*xy){struct output*o=find(ctx,name);if(!o)return -1;xy[0]=o->x;xy[1]=o->y;return 0;}
static void reset_session(struct output *o) {
 if(o->buffer)wl_buffer_destroy(o->buffer);
 if(o->session)ext_image_copy_capture_session_v1_destroy(o->session);
 if(o->source)ext_image_capture_source_v1_destroy(o->source);
 if(o->pixels)munmap(o->pixels,o->size);
 o->buffer=NULL;o->session=NULL;o->source=NULL;o->pixels=NULL;o->size=0;
 o->constraints=o->stopped=o->ready=o->valid=0;o->width=o->height=0;o->format=UINT32_MAX;
}
int pixel_backend(void*ctx,const char*name){struct context*c=ctx;struct output*o=find(c,name);return o&&o->workspace?1:0;}
int pixel_refresh(void*ctx,const char*name){struct context*c=ctx;dispatch(c,0);struct output*o=find(c,name);if(!o)return -1;
 struct ext_workspace_handle_v1 *workspace=NULL;
 if(c->workspace_sources&&c->workspace_manager){workspace=active_workspace(c,o);if(!workspace)return -5;}
 if(o->session&&(o->workspace!=workspace||o->stopped))reset_session(o);
 if(!o->session){
  o->workspace=workspace;
  o->source=workspace?zcosmic_workspace_image_capture_source_manager_v1_create_source(c->workspace_sources,workspace):ext_output_image_capture_source_manager_v1_create_source(c->sources,o->wl);
  o->session=ext_image_copy_capture_manager_v1_create_session(c->capture,o->source,0);
  ext_image_copy_capture_session_v1_add_listener(o->session,&session_listener,o);
  for(int i=0;i<20&&!o->constraints&&!o->stopped;i++)if(dispatch(c,100)<0)return -2;}
 if(o->stopped||!o->constraints||o->format==UINT32_MAX||!o->width||!o->height||o->width>32768||o->height>32768)return -3;
 size_t size=(size_t)o->width*o->height*4;
 if(!o->buffer||o->size!=size||o->buffer_width!=o->width||o->buffer_height!=o->height||o->buffer_format!=o->format){
  if(o->buffer)wl_buffer_destroy(o->buffer);if(o->pixels)munmap(o->pixels,o->size);o->pixels=NULL;o->buffer=NULL;
  int fd=memfd_create("okayu-pixel-buffer",MFD_CLOEXEC);if(fd<0||ftruncate(fd,size)<0){if(fd>=0)close(fd);return -4;}
  o->pixels=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);if(o->pixels==MAP_FAILED){o->pixels=NULL;close(fd);return -4;}
  struct wl_shm_pool*p=wl_shm_create_pool(c->shm,fd,size);o->buffer=wl_shm_pool_create_buffer(p,0,o->width,o->height,o->width*4,o->format);wl_shm_pool_destroy(p);close(fd);o->size=size;o->buffer_width=o->width;o->buffer_height=o->height;o->buffer_format=o->format;o->valid=0;}
 struct ext_image_copy_capture_frame_v1*frame=ext_image_copy_capture_session_v1_create_frame(o->session);ext_image_copy_capture_frame_v1_add_listener(frame,&frame_listener,o);o->ready=0;
 ext_image_copy_capture_frame_v1_attach_buffer(frame,o->buffer);ext_image_copy_capture_frame_v1_damage_buffer(frame,0,0,o->width,o->height);ext_image_copy_capture_frame_v1_capture(frame);
 for(int i=0;i<4&&!o->ready;i++){int r=dispatch(c,o->valid?16:80);if(r<0){o->ready=-1;break;}if(r==0)break;}
 ext_image_copy_capture_frame_v1_destroy(frame);
 wl_display_flush(c->display);
 return o->valid?0:-5;}
static void pixel_coordinates(struct output *o,double x,double y,int *px,int *py) {
 double u=x,v=y;
 switch(o->transform){case 1:u=y;v=1-x;break;case 2:u=1-x;v=1-y;break;case 3:u=1-y;v=x;break;case 4:u=1-x;break;case 5:u=1-y;v=1-x;break;case 6:v=1-y;break;case 7:u=y;v=x;break;}
 *px=(int)(u*o->width);*py=(int)(v*o->height);
 if(*px<0)*px=0;if(*py<0)*py=0;if(*px>=(int)o->width)*px=o->width-1;if(*py>=(int)o->height)*py=o->height-1;
}
static uint32_t pixel_value(struct output *o,int px,int py) {
 if(px<0)px=0;if(py<0)py=0;if(px>=(int)o->width)px=o->width-1;if(py>=(int)o->height)py=o->height-1;
 uint32_t value=((uint32_t*)o->pixels)[(size_t)py*o->width+px];
 return (o->format==WL_SHM_FORMAT_ABGR8888||o->format==WL_SHM_FORMAT_XBGR8888)?((value&255)<<16)|(value&0xff00)|((value>>16)&255):value&0xffffff;
}
int pixel_read(void*ctx,const char*name,double x,double y,uint32_t*color) {
 struct output *o=find(ctx,name);if(!o||!o->valid||!o->pixels||!color)return -1;
 int px,py;pixel_coordinates(o,x,y,&px,&py);*color=pixel_value(o,px,py);return 0;
}
/* The caller owns the buffer. Neighbors are copied in displayed orientation,
 * using integer steps from the exact pixel returned by pixel_read. */
int pixel_region(void*ctx,const char*name,double x,double y,int side,uint32_t*pixels) {
 struct output *o=find(ctx,name);if(!o||!o->valid||!o->pixels||!pixels||side<1||side>145||!(side&1))return -1;
 static const int basis[8][4]={{1,0,0,1},{0,-1,1,0},{-1,0,0,-1},{0,1,-1,0},{-1,0,0,1},{0,-1,-1,0},{1,0,0,-1},{0,1,1,0}};
 if(o->transform>7)return -1;
 int px,py;pixel_coordinates(o,x,y,&px,&py);const int *d=basis[o->transform];
 for(int j=0;j<side;j++)for(int i=0;i<side;i++) {
  int dx=i-side/2,dy=j-side/2;
  pixels[j*side+i]=pixel_value(o,px+d[0]*dx+d[2]*dy,py+d[1]*dx+d[3]*dy);
 }
 return 0;
}
void pixel_close(void*ctx){if(!ctx)return;struct context*c=ctx;
 for(int i=0;i<c->count;i++){reset_session(&c->outputs[i]);if(c->outputs[i].wl)wl_output_destroy(c->outputs[i].wl);}
 for(int i=0;i<c->workspace_count;i++)if(c->workspaces[i].wl)ext_workspace_handle_v1_destroy(c->workspaces[i].wl);
 for(int i=0;i<c->group_count;i++)if(c->groups[i].wl)ext_workspace_group_handle_v1_destroy(c->groups[i].wl);
 if(c->workspace_manager){ext_workspace_manager_v1_stop(c->workspace_manager);wl_proxy_destroy((struct wl_proxy*)c->workspace_manager);}
 if(c->workspace_sources)zcosmic_workspace_image_capture_source_manager_v1_destroy(c->workspace_sources);
 if(c->capture)ext_image_copy_capture_manager_v1_destroy(c->capture);if(c->sources)ext_output_image_capture_source_manager_v1_destroy(c->sources);if(c->shm)wl_shm_destroy(c->shm);if(c->registry)wl_registry_destroy(c->registry);wl_display_disconnect(c->display);free(c);}
