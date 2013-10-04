/*
*
*  FILE: agenda_edit.js
* Copyright (c) 2013, The IETF Trust. See ../../../LICENSE.
*
*   www.credil.org: Project Orlando 2013
*   Author: Justin Hornosty ( justin@credil.org )
*           Michael Richardson <mcr@sandelman.ca>
*
*  Description:
*      This is the main file for the agenda editing page.
*      It contains the document read function that starts everything
*      off, and uses functions and objects from agenda_*.js
*
*/




//////////////-GLOBALS----////////////////////////////////////////

var meeting_number = 0;   // is the meeting name.
var schedule_id    = 0;   // what is the schedule we are editing.
var schedule_owner_href = '';  // who owns this schedule
var is_secretariat = false;
var meeting_objs = {};    // contains a list of session objects -- by session_id
var session_objs = {};    // contains a list of session objects -- by session_name
var slot_status = {};     // indexed by domid, contains an array of ScheduledSessions objects
var slot_objs   = {};     // scheduledsession indexed by id.

var group_objs = {};      // list of working groups
var area_directors = {};  // list of promises of area directors, index by href.

var read_only = true;     // it is true until we learn otherwise.
var days = [];
var legend_status = {};   // agenda area colors.
var load_conflicts = true;
var duplicate_sessions = {};
/********* colors ************************************/

var dragging_color = "blue"; // color when draging events.
var none_color = '';  // when we reset the color. I believe doing '' will force it back to the stylesheet value.
var color_droppable_empty_slot = 'rgb(0, 102, 153)';

// these are used for debugging only.
var last_json_txt   = "";   // last txt from a json call.
var last_json_reply = [];   // last parsed content

var hidden_rooms = [];
var total_rooms = 0; // the number of rooms
var hidden_days = [];
var total_days = 0; // the number of days

/****************************************************/

/////////////-END-GLOBALS-///////////////////////////////////////

/* refactor this out into the html */
$(document).ready(function() {
    initStuff();

   $("#CLOSE_IETF_MENUBAR").click();

});

/* initStuff()
   This is ran at page load and sets up the entire page.
*/
function initStuff(){
    log("initstuff() running...");
    setup_slots();
    directorpromises = mark_area_directors();
    log("setup_slots() ran");
    droppable();

    $.when.apply($,directorpromises).done(function() {
        /* can not load events until area director info has been loaded */
        log("droppable() ran");
        load_events();
        log("load_events() ran");
        find_meeting_no_room();
        listeners();
        droppable();
        duplicate_sessions = find_double_timeslots();

        if(load_conflicts) {
            recalculate(null);
        }
    });

    static_listeners();
    log("listeners() ran");
    calculate_name_select_box();

    start_spin();

    read_only = true;
    log("do read only check");
    read_only_check();
    stop_spin();

    meeting_objs_length = Object.keys(meeting_objs).length;

    /* Comment this out for fast loading */
    //load_conflicts = false;
}

var __READ_ONLY;
function read_only_result(msg) {
    __READ_ONLY = msg;
    is_secretariat = msg.secretariat;

    read_only = msg.read_only;
    console.log("read only", read_only);

    if(!read_only) {
	$("#read_only").css("display", "none");
    }

    if(msg.write_perm) {
        $(".agenda_save_box").css("display", "block");
        if(read_only) {
            $(".agenda_save_box").css("position", "fixed");
            $(".agenda_save_box").css("top", "20px");
            $(".agenda_save_box").css("right", "10px");
            $(".agenda_save_box").css("bottom", "auto");
            $(".agenda_save_box").css("border", "3px solid blue");
        }
    } else {
        $(".agenda_save_box").html("please login to save");
    }

    schedule_owner_href = msg.owner_href;
    // XX go fetch the owner and display it.
    console.log("owner href:", schedule_owner_href);

    empty_info_table();
    listeners();
    droppable();
}

function read_only_check() {
    Dajaxice.ietf.meeting.readonly(read_only_result,
                                    {'meeting_num': meeting_number,
                                     'schedule_id': schedule_id,
                                    });
}

function dajaxice_callback(message) {
    /* if the message is empty, we got nothing back from the server, which probably
       means you are offline.
    */
    console.log("callback: ",message);
    if(message == ""){
	alert("No response from server. Network may be unavailable");
    }
    else{
	stop_spin();
    }
}

function print_all_ss(objs){
    console.log(objs)
}
function get_ss(){
    Dajaxice.ietf.meeting.get_scheduledsessions(print_all_ss);
}


/*
 * Local Variables:
 * c-basic-offset:4
 * End:
 */
