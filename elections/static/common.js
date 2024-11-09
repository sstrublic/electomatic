/* Copyright 2021-2023 Steve Strublic

   This work is the personal property of Steve Strublic, and as such may not be
   used, distributed, or modified without my express consent.
*/

/* Common form JS */


/* Set the top position of the scrollable area */
function setElementTopPosition() {
  var topelem = document.getElementById("top")

  /* Small windows don't need adjustment */
  var small = window.matchMedia("(max-width: 767px)")
  if (small.matches == false) {
    /* Get height of the title element */
    var titleheight = document.getElementById("title").clientHeight;

    /* Store the original top position upon entering the page */
    if (topelem.hasAttribute('originaltop') == false) {
      var pos = parseInt($(topelem).css('top'));
      topelem.setAttribute('originaltop', pos);
    }

    /* Get the original top position of the element so we don't keep growing it each time */
    var pos = parseInt(topelem.getAttribute('originaltop'));

    /* 52 is the empirically determined title height for a single line title */
    var newtop = '' + ((titleheight - 52) + pos) + "px;";

    /* Set the new top position based on the height of the title and the original top position */
    topelem.style = "top:" + newtop;

  } else {
    /* Relative style doesn't have a top position */
    topelem.style = "top:0px;";
  }
}


/* Set a show/hide state for a button that is used to show or hide information. */
function showHide(showbutton, showvalue) {
  if (showvalue == "hide") {
    showvalue = "show";
  } else {
    showvalue = "hide";
  }

  showbutton.value = showvalue;
}

/* Simulate a mouse click */
function simulateClick(field) {
  document.getElementById(field).click();
}

function setStatusColor(judgeid) {

  /* Get the selection for the status field. */
  var statusfield
  if (judgeid == 0) {
    statusfield = document.getElementById('status')
  } else {
    statusfield = document.getElementById('status_' + judgeid)
  }

  var status = statusfield.value

  /* These colors match waht's in the CSS stylesheet. */

  /* 0 (unknown) = grey. */
  if (status == 0) {
      statusfield.setAttribute("style", "color: grey")

  /* 1 (confirmed as a judge) = a specific green. */
  } else if (status == 1) {
    statusfield.setAttribute("style", "color: #238360")

  /* 3 (reserved judge) = blue. */
  } else if (status == 3) {
    statusfield.setAttribute("style", "color: rgb(0, 0, 224)")

  /* The only other status 2 (not available as a judge) = red. */
  } else {
    statusfield.setAttribute("style", "color: rgb(192, 0, 0)")
  }
}

/* Select the field. */
function selectField(elem) {
  elem.select();
}


/* Set the state of the submit button. */
function setSubmitState(state) {
  document.getElementById('savebutton').disabled = !state;
  if (state == true) {
    document.getElementById('savebutton').style = "pointer-events: none;";
  } else {
    document.getElementById('savebutton').style = "";
  }
}


/* Enable the submit button and focus to it. */
function enableSubmit(event) {
  event.preventDefault();
  document.getElementById('confirm').disabled = true;
  document.getElementById('confirm').style = "pointer-events: none;";
  document.getElementById('savebutton').disabled = false;
  document.getElementById('savebutton').focus();
  document.getElementById('savebutton').style = "";
}


/* Enable the confirm button and disable the submit button. */
function reconfirm(event) {
  document.getElementById('confirm').disabled = false;
  document.getElementById('confirm').style = "";
  document.getElementById('savebutton').disabled = true;
  document.getElementById('savebutton').style = "pointer-events: none;";
}

function enableConfirm(event) {
  event.preventDefault();
  reconfirm(event);
}

/* Convert Enter to a simulated tab (shift-enter to shift-tab) by shifting focus to
   the next tab index.
   In this scheme, each input must have a tab index,
    the submit button must be tabindex 0 and the cancel button must have tabindex 1.
*/
function enterToTab(elem, event) {

  if ((event.keyCode == 13) || (event.keyCode == 9)) {
    if (event.keyCode == 9) {
      event.preventDefault();
    }

    /* Disable enter key for entry ID input boxes. */
    else if (event.keyCode == 13) {
      if (elem.tabIndex > 1) {
        event.preventDefault();
      } else {
        return;
      }
    }

    /* Get all tab index elements. */
    /* Sort by tabIndex. */
    var inputs = Array.prototype.slice.call(document.querySelectorAll('[tabIndex]'), 0);
    inputs.sort(function(a,b) {
      return a.tabIndex - b.tabIndex;
    });

    var currindex = elem.tabIndex
    var nextindex

    if (event.shiftKey == true) {
      /* On shift, move to the previous index. When 0, it is the submit button. */
      nextindex = currindex - 1

      /* Wrap to the last entry text box. */
      if (nextindex < 0) {
          nextindex = inputs.length - 1;
      }
    }
    else {
      /* Move to the next index. */
      nextindex = currindex + 1

      /* Wrap at the end of the inputs array to the submit button. */
      if (nextindex == inputs.length) {
          nextindex = 0;
      }
    }

    /* Set focus. */
    inputs[nextindex].focus();

  }
}


/* Check for button enable/disable */
/* Capture escape key for cancel */
window.onkeyup = function(event) {
  var elementname = event.target.name;
  var element = document.getElementById(elementname);

  /* Capture escape key for cancel */
  if (event.keyCode == 27) {
    event.preventDefault();

    if (elementname == "file") {
      document.getElementById(elementname).value = "";
    }

    /* All pages with an club ID use this field. */
    else if ((elementname == "clubid")) {
      document.getElementById(elementname).value = "";
      /* Clear out any judges last names if that page is active */
      /* This is sort of cheating, but not expecting many combinations like this */
      document.getElementById("namesearch").value = "";
      document.getElementById("entrybutton").disabled = true;
    }

    else if (elementname == "namesearch") {
      document.getElementById(elementname).value = "";
      /* Clear out the club Id as well.  This is specific to the move-judges page. */
      document.getElementById("clubid").value = "";
      document.getElementById("eventid").value = "";
      document.getElementById("entrybutton").disabled = true;
    }

    /* All pages with an entry ID use this field. */
    else if (elementname == "username") {
      document.getElementById(elementname).value = "";
      document.getElementById("userbutton").disabled = true;
    }

    /* Only adding entrants uses a class ID entry field. */
    else if (elementname == "voterid") {
      document.getElementById(elementname).value = "";
      document.getElementById("entrybutton").disabled = true;
    }

  } else {
    /* All pages with an entry ID use this field. */
    if ((elementname == "namesearch") || (elementname == "username") || (elementname == 'voterid')) {
      if (element.value.length == 0) {
        document.getElementById("entrybutton").disabled = true;
      }
    }
  }

}

/* Check for button enable/disable */
window.onkeydown = function(event) {
  var elementname = event.target.name;
  var element = document.getElementById(elementname);

  /* All pages with an entry ID use this field. */
  if ((elementname == "clubid") || (elementname == "namesearch") || (elementname == 'voterid')) {
    if (element.value.length > -1) {
      document.getElementById("entrybutton").disabled = false;
    }
  }

  /* All pages with an entry ID use this field. */
  else if ((elementname == "username")) {
    if (element.value.length > -1) {
      document.getElementById("userbutton").disabled = false;
    }
  }
}

function printDiv(divId) {
  var printContents = document.getElementById(divId).innerHTML;
  var originalContents = document.body.innerHTML;

  document.body.innerHTML = printContents;

  window.print();

  document.body.innerHTML = originalContents;
}

function showBallotItemFields() {
  var type = document.getElementById('type');
  var value = type.value;
  var hidden = false;

  if (2 == value) {
    hidden = true;
  }

  document.getElementById("positionslabel").hidden = hidden;
  document.getElementById("positions").hidden = hidden;
  document.getElementById("positionsspacer1").hidden = hidden;
  document.getElementById("positionsspacer2").hidden = hidden;
  document.getElementById("writeinslabel").hidden = hidden;
  document.getElementById("writeins").hidden = hidden;
  document.getElementById("writeinsspacer1").hidden = hidden;
  document.getElementById("writeinsspacer2").hidden = hidden;
}

function auto_grow(element) {
  element.style.height = "5px";
  element.style.height = (element.scrollHeight + 20) + "px";
}
