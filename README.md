# fusionauth-example-python-starlette
Example FusionAuth client application demonstrating user registration and authentication

## Installation

```
pip install -r requirements.txt
```

## Execution

```
uvicorn main:app --reload
```

## About

This is a super-basic attempt at a Starlette application which uses [FusionAuth](https://fusionauth.io/)
for authentication.

The starting point for this was the [Flask example](https://github.com/FusionAuth/fusionauth-example-python-flask)
or more specifically really, [this branch of my fork of the Flask example](https://github.com/scott2b/fusionauth-example-python-flask/tree/session_with_refresh).
Through these explorations in integrating with Flask and Starlette, I made the
decision that FusionAuth's OAuth based workflow is not the right thing for me, and as
such, I will not be submitting the Flask example branch for PR, and do not very
highly recommend enabling `USE_OAUTH` in the current code. The amount of code you would
need to copy into a project for the backend/API based auth workflow is significantly
less than the overall code here, and I've tried to annotate things accordingly.

### OAuth caveats

If you do decide to use the OAuth workflow, please pay attention to the numerous
caveats I have noted in both repositories. The current approach attempts to mitigate
the issues I ran into, but if you believe you can fully solve the problems of JWT
access tokens, then I recommend spending some time with [this flow chart](http://cryto.net/%7Ejoepie91/blog/2016/06/19/stop-using-jwt-for-sessions-part-2-why-your-solution-doesnt-work/).

I have further noted my concerns in my reply to [RFC 7009](https://github.com/FusionAuth/fusionauth-issues/issues/201)
which I believe is worth keeping an eye on. In short, the things I would need to see
implemented in order to consider using OAuth based authentication in FusionAuth would
minimally include:

- Stop using JWTs for access tokens
- Ability to revoke all tokens, (access and refresh) for a given user -- preferrably on a per-application basis.
- Demonstrable administrative authentication revocation workflow which does not respawn deleted users or user registrations due to lingering tokens or sessions.
- Fixing of whatever it is that causes Firefox to initiate downloading of a file during logout.

Note: I have not even begun to explore SSO, which I suspect is prone to some of the
same issues as FusionAuth's builtin OAuth.


### Backend/API based authentication workflow

As-is (with `USE_OAUTH` set to `False`) the current project seems more secure to me. I
am not a security expert, but so far I don't see a reason not to use this approach if
the workflow suffices for your needs. It's a bit of additional work: you have to build 
your own login form, for example, but I think it is worth it. I do recommend:

- Use server-side session management (a basic filesystem based approach is shown. The same library supports Redis)
- Only serve your site over https 
- Use some kind of csrf checking (not demonstrated here)

Note that it is possible to use FusionAuth's builtin registration instead of doing an
API call, for instance by ensuring self-registered users do not have any default
accesses to the FusionAuth platform ... but I still think it is worth simply building
your own registration forms and making the register API call on the backend.


## General Use case

FusionAuth is a full featured and extremely flexible platform for handling not only
user authentication and application registration, but also things like groups, ACL, etc.
I have not even begun to explore the range or depth of the possibilities for
authentication or authorization. The use case explored here is a simple one: self-registered
user authentication for which sessions and authorization are handled by a "traditional"
web application. There is a lot of capability in FusionAuth I simply have not yet
explored, but also probably won't until I see usable OAuth and SSO workflows.

## Additional notes

### `logout` API calls

As noted in the comments: the `logout` call to the API does not really seem to do
anything even when the refresh token is explicitly passed for revocation. Instead,
revoke refresh tokens explicitly via a call to `revoke_refresh_token` as shown.

### Apache license

I tend to reach for MIT in most of my projects, but for no particular reason. I have
attached an Apache license to this because there are bound to be some lingering
copy-pastes from the [Flask example](https://github.com/FusionAuth/fusionauth-example-python-flask)
which started me on this journey and which uses the Apache license.
