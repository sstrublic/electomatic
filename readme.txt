The Ballot-O-Matic voter data entry system automates the tallying of ballot
entries based on voter data for individual entries in classes.

1.1	Operations Overview
The Ballot-O-Matic is designed to provide a simple and efficient means to
manage classes, entrants in classes, and voting for events like car and
motorcycle shows.  Access to the most commonly used operations is performed
through menus and buttons on each page to minimize ‘hunting’ for the next
most likely thing to do.

1.1.1	Classes and Entries
Entries (the things being judged) are organized into Classes for voting.
Classes can be any desired grouping – by marque, model, age, or any
arbitrarily defined criteria.  The Class simply provides the grouping.
Entries are defined by an Owner (person’s first and last name), a year, marque,
series (model) and color.

1.1.2	Voting
1.1.2.1	Popular Vote Voting
Shows typically offer a simple ‘popular vote’ style voting system, where a
single Entry is chosen per Class and the Entry with the most votes in its Class
is the winner, followed by 2nd, 3rd, etc..  Ballot-O-Matic’s Class Choice
voting supports this voting style with a configurable number of places per
Class.

Many shows also offer a “people’s choice” award, where the public and show
participants vote for their favorite Entry.  Ballot-O-Matic’s People’s Choice
voting supports this voting method.

1.1.2.2	Category Voting
Some shows may make a more detailed evaluation per Class, scoring Entries by
categories and tallying the results.  Ballot-O-Matic’s Class voting supports
category-based voting, albeit with a fixed set of categories that are commonly
used for this voting style.  Ballot-O-Matic also offers a judging format called
‘Peer Judging’ that allows show participants to score Entries through category-
based voting, with assignment of participants to judge Classes and collection
of ballots.

1.1.3	Results
As votes are entered for each Entry, Ballot-O-Matic automatically updates
totals for each voting method.  Results are available at any time and show
up-to-date scoring, totals and placement of Entries within Classes as well as
“people’s choice” votes.  When all voting is complete, determining awards is as
simple as viewing the results.  Ballot-O-Matic sorts the results within each
Class and highlights winners based on the configured number of places for each
Class, as well as the winner of the “people’s choice” voting.

1.1.4	Users
Users of Ballot-O-Matic are organized into a few functional roles, to allow for
system administration, entry of votes and general public access.  Non-admin
roles are restricted to prevent accidental changes while gathering and
recording votes.  Users have a login to allow for tracking of activity for
audit purposes.

1.1.5	Import and Export
When dealing with a large number of classes and entries, manually entering each
one can take some time even if a process is efficient.  Ballot-O-Matic offers an
import capability to configure most of the information that can be entered
through the application interface.  Show organizers track participants as they
sign up and will change class groupings frequently as the makeup of a show’s
participants evolves.  Oftentimes, this is done with a spreadsheet of some other
workbook.  Ballot-O-Matic provides an Excel-format template to organize Classes
and Entries for import, which can save a lot of reconfiguration effort and make
setup nearly a one-click operation.  The format of event data is described in
the Ballot-O-Matic Event Data Guide.

Once the show is over, saving the results for future reference is essential for
seeding future show advertising and targeting of future participants.
Ballot-O-Matic supports an export feature to Excel workbook format, saving the
complete state of all Classes, Entries and Votes.  Results may also be exported
for recordkeeping purposes.

Ballot-O-Matic also allows reset to default (erase all data) to allow for
experimentation and validation of data prior to starting the show.

1.1.6	Auditing
Ballot-O-Matic logs all activities to file, with each activity having a user
association along with a record of the action and results of that action.

Ballot-O-Matic works by having people enter votes from a paper ballot.  Each
Class, Class Choice and Survivor vote entry has a unique ID, which is to be
recorded on the paper ballot and is captured in logs.  This does a couple of
important things:  It allows for anonymity since the ID does not have an
associated name, and it allows for verification and correction as needed by
comparing the paper ballot to the recorded vote.

It is possible to reconstruct every action taken by every user with the data
entered and rebuild the complete voting record.
